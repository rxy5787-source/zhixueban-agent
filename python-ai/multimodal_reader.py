"""知学伴 · 多模态资料解析模块。

批量导入的文件中，普通文字由 Python 提取；图片、包含图表或扫描内容的
PDF页面由本地 qwen3-vl:2b 辅助理解；OCR为文字读取提供补充。

重要：视觉模型的描述是辅助性观察，不是已验证事实，也不是标准答案。
"""

from __future__ import annotations

import base64
import hashlib
import io
import json
import os
import re
import uuid
import zipfile
from pathlib import Path

import pymupdf
import requests

AUDIT = None
from docx import Document
from PIL import Image, UnidentifiedImageError

OLLAMA_CHAT_URL = "http://127.0.0.1:11434/api/chat"
VISION_MODEL = "qwen3-vl:2b-instruct"
MAX_PDF_PAGES = 5  # 初次测试只处理前5页
MAX_VISION_CALLS_PER_FILE = 3  # 限制每份资料的视觉推理次数
MAX_WORD_IMAGES = 4  # 初次测试只处理前4张支持的图片
MAX_IMAGE_EDGE = 1200  # 发送模型前限制图像分辨率
VISION_TIMEOUT = 600

# 避免重复初始化OCR引擎
_ocr_engine = None


def _to_jpeg_bytes(image_bytes: bytes) -> bytes:
    """压缩图片以减少HTTP负载和本地模型内存压力。"""
    with Image.open(io.BytesIO(image_bytes)) as im:
        im = im.convert("RGB")
        im.thumbnail((MAX_IMAGE_EDGE, MAX_IMAGE_EDGE))
        out = io.BytesIO()
        im.save(out, format="JPEG", quality=83)
        return out.getvalue()


def _ocr_lines(image_bytes: bytes) -> list[dict]:
    global _ocr_engine
    if _ocr_engine is None:
        from rapidocr import RapidOCR

        _ocr_engine = RapidOCR(
            params={
                'EngineConfig.onnxruntime.intra_op_num_threads': 2,
                'EngineConfig.onnxruntime.inter_op_num_threads': 1,
                'Global.log_level': 'warning',
            }
        )
    result = _ocr_engine(image_bytes)
    return [
        {'text': str(text).strip(), 'score': float(score)}
        for text, score in zip(result.txts or [], result.scores or [])
    ]


def _ocr(image_bytes: bytes) -> str:
    return '\n'.join(row['text'] for row in _ocr_lines(image_bytes)).strip()


def _ocr_section(raw, location, cache_dir=None):
    # OCR scores indicate recognition confidence, not factual correctness.
    # Cache is keyed by image bytes and parser/model profile, never by filename.
    key = hashlib.sha256(b'rapidocr-3.10-v6-small-160dpi-lines-085-v1\0' + raw).hexdigest()
    cache = Path(cache_dir) / f'{key}.json' if cache_dir else None
    data = None
    if cache and cache.is_file():
        try:
            candidate = json.loads(cache.read_text(encoding='utf-8'))
            if candidate.get('version') == 1 and isinstance(candidate.get('lines'), list):
                data = candidate
        except (OSError, ValueError):
            pass
    if data is None:
        data = {'version': 1, 'lines': _ocr_lines(raw)}
        if cache:
            cache.parent.mkdir(parents=True, exist_ok=True)
            temporary = cache.with_suffix('.' + uuid.uuid4().hex + '.tmp')
            try:
                temporary.write_text(json.dumps(data, ensure_ascii=False), encoding='utf-8')
                os.replace(temporary, cache)
            finally:
                temporary.unlink(missing_ok=True)
    kept, low, blanks = [], 0, 0
    for row in data['lines']:
        text = row['text'].strip()
        if not text:
            continue
        if row['score'] < 0.85:
            low += 1
            continue
        # Do not turn an unfilled formula/answer prompt into a source fact.
        incomplete = re.search(r'(?:[=＝:：，,]|等于|截|_{2,}|\.{3,}|…)$', text)
        exercise = re.search(
            r'[?？]|(?:^|[，,:：])(?:问|求)(?:几|多少|差距|时间|年|距离).{0,12}$', text
        )
        if incomplete or exercise:
            blanks += 1
            continue
        kept.append(row)
    text = '\n'.join(row['text'] for row in kept)
    section = _section(text, location + ' · OCR文字', False, False)
    section.update(
        extraction='ocr',
        textOnly=True,
        visionStatus='ocr_text_only',
        ocrConfidence=round(sum(r['score'] for r in kept) / len(kept), 4) if kept else 0,
        ocrLines=len(kept),
        lowConfidenceLines=low,
        incompleteLines=blanks,
        parsingNote='已识别扫描文字，仅依据文字出题；识别结果可能有错，请对照原页核对。',
    )
    if not text:
        section['parsingError'] = (
            '未识别到清晰、完整的文字；可能是纯图形、空白页或未填写的默写表，请补充完整资料。'
        )
    return section


def _automatic_image(raw, location, cache_dir, vision_fallback):
    try:
        section = _ocr_section(raw, location, cache_dir)
    except Exception as exc:
        section = _section('', location)
        section['parsingError'] = f'OCR失败：{str(exc)[:200]}'
    if section['text'].strip() or not vision_fallback:
        return section
    try:
        description = describe_image(raw)
        visual = _section(description, location + ' · 视觉观察', True, True)
        visual.update(
            extraction='vision',
            parsingNote='仅为视觉模型观察，未经原图事实验证，不进入可练习题库。',
        )
        return visual
    except Exception as exc:
        section['parsingError'] = (
            f"{section.get('parsingError', '无清晰OCR文字')}；视觉模型失败：{str(exc)[:220]}"
        )
        return section


def iter_automatic_sections(path, cache_dir=None, on_progress=None, vision_fallback=False):
    """Read lazily: reaching the target or cancelling never OCRs remaining pages."""
    path = Path(path)
    from backend.file_storage import validate_file

    validate_file(path, path.name)
    progress = on_progress or (lambda stage: None)
    if path.suffix.lower() == '.pdf':
        with pymupdf.open(str(path)) as pdf:
            for index in range(min(len(pdf), MAX_PDF_PAGES)):
                location = f'PDF第{index+1}页'
                text = pdf[index].get_text('text', sort=True).strip()
                if len(text) >= 40:
                    progress('提取文字 · ' + location)
                    section = _section(text, location)
                    section.update(
                        extraction='text',
                        textOnly=True,
                        parsingNote='仅使用可提取文字，图片和图表不作为事实依据。',
                    )
                else:
                    progress('正在识别扫描文字 · ' + location)
                    try:
                        raw = pdf[index].get_pixmap(dpi=160, alpha=False).tobytes('png')
                        section = _automatic_image(raw, location, cache_dir, vision_fallback)
                    except Exception as exc:
                        section = _section('', location)
                        section.update(
                            extraction='ocr', parsingError=f'文字识别失败：{str(exc)[:200]}'
                        )
                section.update(page=index + 1, pagesAvailable=len(pdf), pagesLimit=MAX_PDF_PAGES)
                yield section
    elif path.suffix.lower() in {'.jpg', '.jpeg', '.png', '.bmp', '.webp'}:
        progress('正在识别图片文字')
        yield _automatic_image(path.read_bytes(), '原始图片', cache_dir, vision_fallback)
    elif path.suffix.lower() == '.docx':
        # Text already present in Word remains usable even when it embeds images.
        doc = Document(str(path))
        pieces = [p.text.strip() for p in doc.paragraphs if p.text.strip()]
        pieces.extend(
            ' | '.join(cell.text.strip() for cell in row.cells)
            for table in doc.tables
            for row in table.rows
        )
        if any(pieces):
            section = _section('\n'.join(pieces), 'Word正文与表格')
            section.update(extraction='text', textOnly=True)
            yield section
        with zipfile.ZipFile(path) as archive:
            names = sorted(
                n
                for n in archive.namelist()
                if n.startswith('word/media/')
                and Path(n).suffix.lower() in {'.png', '.jpg', '.jpeg', '.bmp', '.webp'}
            )
            seen = set()
            for name in names[:MAX_WORD_IMAGES]:
                raw = archive.read(name)
                digest = hashlib.sha256(raw).hexdigest()
                if digest in seen:
                    continue
                seen.add(digest)
                progress('正在识别 Word 图片文字')
                yield _automatic_image(
                    raw, 'Word图片 ' + Path(name).name, cache_dir, vision_fallback
                )
    else:
        yield from read_multimodal_file(path)


def describe_image(image_bytes: bytes) -> str:
    """真实调用 qwen3-vl:2b 的 Ollama 视觉接口，传入 base64 图像。"""
    encoded = base64.b64encode(_to_jpeg_bytes(image_bytes)).decode("ascii")
    payload = {
        "model": VISION_MODEL,
        "messages": [
            {
                "role": "user",
                "content": (
                    "你正在辅助解析一份学习资料图片。只描述能从图中观察到的教学内容、"
                    "图表坐标轴、曲线趋势、图形元素、公式和可见的文字。"
                    "如有几何关系，说明你能直接看出的关系，不要臆测隐藏的数值或解答。"
                    "对看不清、不确定的内容直接写『不确定』。"
                    "不要自行生成题目。使用中文，尽量简洁（300字以内）。"
                ),
                "images": [encoded],
            }
        ],
        "stream": False,
        "think": False,
        "options": {"temperature": 0, "num_ctx": 4096, "num_predict": 800},
    }
    response = requests.post(OLLAMA_CHAT_URL, json=payload, timeout=(10, VISION_TIMEOUT))
    response.raise_for_status()
    data = response.json()
    if AUDIT:
        AUDIT("vision", data)
    message = data.get("message") if isinstance(data, dict) else None
    content = message.get("content") if isinstance(message, dict) else None
    if not isinstance(content, str):
        raise ValueError("视觉模型响应缺少文本 message.content")
    description = content.strip()
    if not description:
        raise ValueError("视觉模型返回空文本")
    return description


def _section(
    text: str, location: str, is_visual: bool = False, requires_visual: bool = False
) -> dict:
    return {
        "text": text.strip(),
        "location": location,
        "visualAssisted": is_visual,
        "requiresVisual": requires_visual,
        "visionStatus": "used" if is_visual else "not_used_or_failed",
    }


def _read_image(path: Path) -> list[dict]:
    raw = path.read_bytes()
    # 优先OCR，视觉辅助图形理解；OCR失败后仍继续视觉分析。
    try:
        ocr = _ocr(raw)
    except Exception as exc:
        print(f"  图片OCR失败，仍尝试视觉理解：{exc}")
        ocr = ""
    try:
        vision = describe_image(raw)
    except Exception as exc:
        print(f"  视觉分析失败，保留OCR结果：{exc}")
        vision = ""
    if not ocr and not vision:
        raise ValueError("OCR和视觉模型均未能解析此图片")
    text = "\n".join(
        filter(
            None,
            [
                f"【图片OCR文字】\n{ocr}" if ocr else "",
                f"【视觉模型观察（未经事实核实）】\n{vision}" if vision else "",
            ],
        )
    )
    return [_section(text, "原始图片", bool(vision), True)]


def _read_pdf(path: Path, automatic_only: bool = False) -> list[dict]:
    sections = []
    with pymupdf.open(str(path)) as pdf:
        if len(pdf) > MAX_PDF_PAGES:
            print(f"  PDF共{len(pdf)}页；测试模式只处理前{MAX_PDF_PAGES}页")
        remaining_vision = MAX_VISION_CALLS_PER_FILE
        for page_index in range(min(len(pdf), MAX_PDF_PAGES)):
            page = pdf[page_index]
            location = f"PDF第{page_index + 1}页"
            text = page.get_text("text", sort=True).strip()
            # 图表可能是嵌入图像，也可能是PDF矢量绘制；检测两类。
            has_image = bool(page.get_images(full=True))
            has_drawings = len(page.get_drawings()) >= 4
            need_vision = len(text) < 40 or has_image or has_drawings
            if automatic_only and need_vision:
                section = _section(text, location, False, True)
                section['visionStatus'] = 'skipped_visual_unverified'
                sections.append(section)
                continue
            pix_bytes = None
            if need_vision:
                pix_bytes = page.get_pixmap(dpi=120, alpha=False).tobytes("png")
            if len(text) < 40 and pix_bytes:
                try:
                    text = _ocr(pix_bytes)
                except Exception as exc:
                    print(f"  {location} OCR失败：{exc}")
            vision = ""
            if need_vision and remaining_vision > 0 and pix_bytes:
                remaining_vision -= 1
                try:
                    vision = describe_image(pix_bytes)
                    print(f"  {location}：已调用Qwen3-VL")
                except Exception as exc:
                    print(f"  {location}视觉分析失败，保留提取文本：{exc}")
            if text or vision:
                combined = "\n".join(
                    filter(
                        None,
                        [
                            f"【页面提取文字】\n{text}" if text else "",
                            f"【视觉模型观察（未经事实核实）】\n{vision}" if vision else "",
                        ],
                    )
                )
                sections.append(_section(combined, location, bool(vision), need_vision))
            else:
                print(f"  {location}没有识别到有效信息")
        if remaining_vision == 0:
            print("  提示：当前文件已达到视觉模型调用上限，后续图页可能只保留文字")
    return sections


def _read_word(path: Path, automatic_only: bool = False) -> list[dict]:
    doc = Document(str(path))
    pieces = []
    for p in doc.paragraphs:
        if p.text.strip():
            pieces.append(p.text.strip())
    for table in doc.tables:
        for row in table.rows:
            value = " | ".join(cell.text.strip() for cell in row.cells)
            if value.strip(" |"):
                pieces.append(value)
    sections = []
    if pieces:
        sections.append(_section("\n".join(pieces), "Word正文与表格"))
    # docx是ZIP容器，word/media保存常见内嵌图片；VML/浮动对象、
    # 特殊图表、公式不保证完整，需要时将docx转PDF补充检查。
    seen_digests = set()
    image_count = 0
    with zipfile.ZipFile(path) as zf:
        names = sorted(n for n in zf.namelist() if n.startswith("word/media/"))
        if names:
            for section in sections:
                section["requiresVisual"] = True
        if automatic_only and names:
            if not sections:
                sections.append(_section('', 'Word图片', False, True))
            for section in sections:
                section['visionStatus'] = 'skipped_visual_unverified'
            return sections
        if len(names) > MAX_WORD_IMAGES:
            print(f"  Word含{len(names)}张媒体文件；本次最多尝试{MAX_WORD_IMAGES}张")
        for name in names:
            if image_count >= min(MAX_WORD_IMAGES, MAX_VISION_CALLS_PER_FILE):
                break
            if Path(name).suffix.lower() not in {".png", ".jpg", ".jpeg", ".bmp", ".webp"}:
                continue
            raw = zf.read(name)
            digest = hashlib.sha256(raw).hexdigest()
            if digest in seen_digests:
                continue
            seen_digests.add(digest)
            image_count += 1
            try:
                ocr = _ocr(raw)
            except Exception:
                ocr = ""
            try:
                visual = describe_image(raw)
            except (requests.RequestException, UnidentifiedImageError, ValueError) as exc:
                print(f"  Word图片 {name} 视觉分析失败：{exc}")
                visual = ""
            content = "\n".join(
                filter(
                    None,
                    [
                        f"【图片OCR文字】\n{ocr}" if ocr else "",
                        f"【视觉模型观察（未经事实核实）】\n{visual}" if visual else "",
                    ],
                )
            )
            if content:
                sections.append(
                    _section(content, f"Word图片：{Path(name).name}", bool(visual), True)
                )
    return sections


def read_multimodal_file(path: Path, automatic_only: bool = False) -> list[dict]:
    """统一返回带来源位置和视觉标记的内容块。"""
    path = Path(path)
    if automatic_only:
        return list(iter_automatic_sections(path))
    from backend.file_storage import validate_file

    validate_file(path, path.name)
    suffix = path.suffix.lower()
    print(f"\n解析：{path.name}")
    if suffix in {".jpg", ".jpeg", ".png", ".bmp", ".webp"}:
        if automatic_only:
            section = _section('', '原始图片', False, True)
            section['visionStatus'] = 'skipped_visual_unverified'
            return [section]
        return _read_image(path)
    if suffix == ".pdf":
        return _read_pdf(path, automatic_only)
    if suffix == ".docx":
        return _read_word(path, automatic_only)
    if suffix == ".txt":
        try:
            value = path.read_text(encoding="utf-8-sig")
        except UnicodeDecodeError:
            value = path.read_text(encoding="gb18030")
        return [_section(value, "TXT全文")] if value.strip() else []
    raise ValueError(f"不支持的文件类型：{suffix}（旧版.doc需先另存为.docx或PDF）")
