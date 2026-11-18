import json
from pathlib import Path


import requests
from backend.model_status import checked_model_response
AUDIT = None
import pymupdf
from docx import Document



# =====================================
# 1. 基础配置
# =====================================

# Ollama本地接口
OLLAMA_URL = "http://127.0.0.1:11434/api/chat"

# 千问模型
MODEL_NAME = "qwen3:1.7b"

# 当前Python项目文件夹
BASE_DIR = Path(__file__).resolve().parent

# 每段最多输入多少字符
MAX_CHARS = 1500

# 初次测试最多处理3段
MAX_PARTS = 3

# 初次测试PDF最多读取10页
MAX_PDF_PAGES = 10

# 每段生成多少道题
QUESTIONS_PER_PART = 3

# OCR引擎
ocr_engine = None


# =====================================
# 2. 图片文字识别
# =====================================

def recognize_image(image_data):

    global ocr_engine

    if ocr_engine is None:
        print("正在初始化OCR文字识别引擎...")
        from rapidocr import RapidOCR
        ocr_engine = RapidOCR()

    result = ocr_engine(image_data)

    texts = result.txts or []

    return "\n".join(texts).strip()


# =====================================
# 3. 读取Word文件
# =====================================

def read_word(file_path):

    print("正在读取Word文件...")

    from backend.file_storage import validate_file
    validate_file(Path(file_path), Path(file_path).name)
    document = Document(str(file_path))

    content = []

    # 提取普通段落
    for paragraph in document.paragraphs:

        text = paragraph.text.strip()

        if text:
            content.append(text)

    # 提取表格
    for table in document.tables:

        for row in table.rows:

            cells = [
                cell.text.strip()
                for cell in row.cells
            ]

            if any(cells):
                content.append(" | ".join(cells))

    return "\n".join(content)


# =====================================
# 4. 读取PDF文件
# =====================================

def read_pdf(file_path):

    print("正在读取PDF文件...")

    content = []

    with pymupdf.open(str(file_path)) as pdf:

        total_pages = len(pdf)

        pages_to_read = min(
            total_pages,
            MAX_PDF_PAGES
        )

        print(f"PDF总页数：{total_pages}")

        if total_pages > MAX_PDF_PAGES:
            print(
                f"测试模式：暂时只读取前"
                f"{MAX_PDF_PAGES}页"
            )

        for page_number in range(pages_to_read):

            page = pdf[page_number]

            print(
                f"正在处理第{page_number + 1}页..."
            )

            # 优先直接提取PDF文字
            text = page.get_text(
                "text",
                sort=True
            ).strip()

            # 如果没有足够的可提取文字
            # 则尝试OCR识别
            if len(text) < 20:

                print("检测到可能是扫描页面，正在OCR识别...")

                pix = page.get_pixmap(
                    dpi=150,
                    alpha=False
                )

                image_bytes = pix.tobytes("png")

                text = recognize_image(image_bytes)

            if text:

                content.append(
                    f"\n【第{page_number + 1}页】\n{text}"
                )

    return "\n".join(content)


# =====================================
# 5. 读取图片文件
# =====================================

def read_image(file_path):

    print("正在识别图片中的文字...")

    # 以字节方式读取，兼容中文文件路径
    image_bytes = file_path.read_bytes()

    text = recognize_image(image_bytes)

    return text


# =====================================
# 6. 根据文件类型自动选择读取方式
# =====================================

def read_file(file_path):

    suffix = file_path.suffix.lower()

    if suffix == ".docx":

        return read_word(file_path)

    elif suffix == ".pdf":

        return read_pdf(file_path)

    elif suffix in [
        ".jpg",
        ".jpeg",
        ".png",
        ".bmp"
    ]:

        return read_image(file_path)

    elif suffix == ".txt":

        return file_path.read_text(
            encoding="utf-8-sig"
        )

    else:

        raise ValueError(
            f"暂不支持这种文件格式：{suffix}"
        )


# =====================================
# 7. 文本分段
# =====================================

def split_text(text):

    text = text.strip()

    parts = []

    for i in range(0, len(text), MAX_CHARS):

        part = text[i:i + MAX_CHARS]

        if part.strip():
            parts.append(part)

    return parts


# =====================================
# 8. 调用千问自动生成题目
# =====================================

def generate_questions(material, question_count=None, knowledge_points=None, timeout=600, raw_candidates=False, feedback=None, requirements="", difficulty=0, used_evidence=None, allow_rule_generation=True, compact_source=False):

    requested = question_count or QUESTIONS_PER_PART
    # Evidence is copied by index; a small model must not freely rewrite it.
    import re
    segments=[m.group().strip() for m in re.finditer(r'[^。；;\n]+[。；;]?',material)
              if len(re.sub(r'\W','',m.group()))>=8 and not re.search(r'[=＝:：，,]$',m.group().strip())]
    if compact_source:
        from backend.practice_quality import source_units
        segments=source_units(material)
    if used_evidence:segments=[segment for segment in segments if segment not in used_evidence]
    if not segments:return []
    requested=min(requested,len(segments))
    from backend.literal_evidence import question_hints,questions_from_facts
    grounded=questions_from_facts(segments,knowledge_points,requested,difficulty,requirements) if allow_rule_generation else []
    if grounded and allow_rule_generation:
        if AUDIT:AUDIT('rule_generation',{'method':'source_quantity_template_v1','questions':grounded})
        return grounded
    hints=question_hints(segments)
    planned={hint['sourceIndex']:hint['questionFocus'] for hint in hints}
    quantity_only=len(planned)==len(segments)
    point_names = [p["name"] for p in knowledge_points] if knowledge_points else None
    prompt = f"""依据下方资料生成{requested}道中文单选题。
命题步骤：先选资料中一句明确的定义或事实，再围绕这一个事实提出问题；正确选项表达该事实，另外三个选项表达不同且不成立的含义。四个选项必须相互排斥。
优先提问一个术语的作用、含义或先后顺序。四个选项采用简洁的概念描述，每项15字以内。不要把完整SQL语句作为选项。
题干必须是真正的疑问句，以中文问号？结束，询问“什么、哪一种、哪一项”。不能把原文结论作为题干，也不能把陈述句简单加问号。题干只提出问题，答案内容留在选项。
每题须有唯一答案、知识点和难度。sourceIndex 必须选择直接支撑正确答案的原文编号，程序会把该原句作为解析。不要输出或改写解析文字，不可扩展其他选项的归因。题干必须独立完整，证据只能来自资料。
资料可能是扫描件的OCR文字。只考查资料中已经完整写出的事实；不得补全留空的公式、答案或残句，不得把坐标、标题或图例推断成图形关系。不得出必须看原图、表格位置或几何图形才能回答的题。没有足够依据可以少出题，不能编造内容凑题数。
原资料中已有的题号、选项、答案字母和无题干的题目片段不能作为考点或证据。不要问“问题1的正确答案是什么”。
对于明确写出条件和数量的规则，请直接考查该条件对应的数量，题干写全原文条件和动作，选项用不同的数量和同一单位。
同一条原文不要重复出题。JSON字段：questions数组；每题含 sourceIndex、question、options（A/B/C/D）、answer、knowledgePoint、difficulty（简单/中等/困难）。
"""
    if knowledge_points:
        prompt += "\n本次仅考查以下知识点，knowledgePoint 必须逐字采用目录名称：" + json.dumps(knowledge_points,ensure_ascii=False)
    if feedback:
        prompt += "\n上轮质检指出以下问题，请重新选取一个明确事实，避免这些问题：" + feedback
    prompt += "\n【编号资料】\n" + json.dumps([{'sourceIndex':i,'text':text} for i,text in enumerate(segments)],ensure_ascii=False) + "\n围绕明确事实生成互斥的单选题，sourceIndex 必须指向该题直接依据的原句。只返回JSON。"
    prompt += "\n【学习者本次出题要求】\n" + requirements + f"\n本次调用最多生成{requested}道四选一单选题，难度为" + (["按资料选择","简单","中等","困难"][difficulty]) + "。重点和提问方式遵循用户要求，但不得超出资料、知识点目录、题型与质量约束。题数和难度以本段结构化参数为准。"
    prompt += '\nsourceIndex只是程序内部的证据定位字段，不能成为考点。禁止询问原文第几句、哪句原文或句子编号；选项必须是知识内容。题干不能直接泄露答案。'
    if hints:
        prompt += '\n原文明示的数量规则可以按以下方向提问，请据原文作答并生成四个互异的数量选项，不要考查句子编号：'+json.dumps(hints,ensure_ascii=False)
    if quantity_only:
        prompt += '\n本段题干已按原文完整条件和动作确定。只为各 sourceIndex 的既定题干生成四个互异的数量选项、标准答案、知识点和难度，不要自行改写题干。'
    if compact_source:
        source = '\n'.join(f'{i}: {unit}' for i, unit in enumerate(segments))
        level = ['按资料选择', '简单', '中等', '困难'][difficulty]
        prompt = f'''依据资料，按要求出至多{requested}道四选一单选题，难度{level}。优先给出任务或现象，考判断该用哪个部件、机制或规则。四个选项要互不重复，优先采用易混的同类概念。题干条件完整、以问号结尾且不含答案。每题引用不同的原文编号，覆盖不同考点。knowledgePoint写简短的专业术语；sourceIndex填写直接支持答案的原文编号。跳过残句、缺条件的公式和图表；依据不足可少出。禁止考题号或原文位置。只输出JSON。
要求：{requirements}
编号资料：
{source}'''
        prompt += (
            '\n作答前核对：先从引用原句找出问题的唯一答案，再把这个含义写进正确选项。'
            '不要把原句或整段资料复制为题干，不要询问原文未说明的原因、过程或细节。'
            '例如原文“某器件用于保存中间结果”，可问“需要暂存中间结果时使用哪类器件？”；'
            '选项中必须有原文明示的那类器件。这个例子只示范命题方式。'
            '若考某概念的作用，正确选项须保留原文的关键动作和对象，不能改写成另一种作用。'
            '按用户使用的语言出题，专有术语可以保留原文写法。'
        )
        if len(segments) >= requested * 3 and requested > 1:
            ranges = [f'{i * len(segments) // requested}–{(i + 1) * len(segments) // requested - 1}' for i in range(requested)]
            prompt += '\n若学习者未限定具体考点，优先从这些编号区间各选一个有完整依据的不同考点：' + '、'.join(ranges)
        if point_names:
            prompt += '\n知识点限用：' + '、'.join(point_names)
        if hints:
            prompt += '\n数量题沿用这些完整题干，选项使用相同单位和不同数值：' + json.dumps(hints,ensure_ascii=False)
        if feedback:
            prompt += '\n避免上一批的问题：' + feedback
    text = {"type":"string","minLength":1}
    props = {"sourceIndex":{"type":"integer","enum":list(range(len(segments)))},"question":text,"options":{"type":"object","properties":{x:text for x in "ABCD"},"required":list("ABCD"),"additionalProperties":False},"answer":{"type":"string","enum":list("ABCD")},"knowledgePoint":{"type":"string","enum":point_names} if point_names else text,"difficulty":{"type":"string","enum":(["简单","中等","困难"] if not difficulty else [["简单","中等","困难"][difficulty-1]])}}
    props['question']={'type':'string','minLength':6,'pattern':'[？?]$'}
    if quantity_only:props.pop('question')
    schema = {"type":"object","properties":{"questions":{"type":"array","minItems":0,"maxItems":requested,"items":{"type":"object","properties":props,"required":list(props),"additionalProperties":False}}},"required":["questions"],"additionalProperties":False}
    data = {"model":MODEL_NAME,"messages":[{"role":"user","content":prompt}],"stream":False,"think":False,"format":schema,"options":{"temperature":0.35 if compact_source else 0.6,"num_ctx":4096,"num_predict":1400 if compact_source else 1600}}

    print("正在调用本地千问模型...")

    response = requests.post(
        OLLAMA_URL,
        json=data,
        timeout=(10, timeout)
    )

    checked_model_response(response,MODEL_NAME)

    result = response.json()
    if AUDIT: AUDIT("generation", result)

    content = result["message"]["content"]

    question_data = json.loads(content)

    questions = question_data.get("questions")

    if not isinstance(questions, list):
        raise ValueError(
            "模型未返回有效的questions列表"
        )

    for question in questions:
        if isinstance(question,dict):
            index=question.pop('sourceIndex',None)
            question['explanation']=segments[index] if type(index) is int and 0<=index<len(segments) else ''
            if type(index) is int and index in planned:
                question['question']=planned[index]
                question['questionConstruction']='source_quantity_template_v1'
    if raw_candidates:
        return questions

    # 基础JSON结构检查
    valid_questions = []

    for question in questions:

        if not isinstance(question, dict):
            continue

        options = question.get("options")

        if not isinstance(options, dict):
            continue

        required_options = {"A", "B", "C", "D"}

        if not required_options.issubset(options.keys()):
            continue

        if not isinstance(question.get("answer"), str) or question["answer"] not in required_options:
            continue

        required_fields = [
            "question",
            "explanation",
            "knowledgePoint",
            "difficulty"
        ]

        if not all(
            isinstance(question.get(field), str)
            and question.get(field).strip()
            for field in required_fields
        ):
            continue

        valid_questions.append(question)

    return valid_questions


# =====================================
# 9. 主程序
# =====================================

def main():

    from tkinter import Tk, filedialog

    print("=" * 50)

    print("知学伴 - 多格式学习资料智能出题系统")

    print("=" * 50)

    # 创建文件选择窗口
    root = Tk()

    root.withdraw()

    root.attributes("-topmost", True)

    file_name = filedialog.askopenfilename(

        title="请选择学习资料",

        filetypes=[
            (
                "所有支持的文件",
                "*.pdf *.docx *.jpg *.jpeg *.png *.bmp *.txt"
            ),
            ("PDF文件", "*.pdf"),
            ("Word文件", "*.docx"),
            (
                "图片文件",
                "*.jpg *.jpeg *.png *.bmp"
            ),
            ("文本文件", "*.txt")
        ]
    )

    root.destroy()

    if not file_name:

        print("没有选择文件，程序结束。")
        return

    file_path = Path(file_name)

    print("\n选择的文件：")
    print(file_path)

    # 读取文件
    material = read_file(file_path)

    if not material.strip():

        print("没有提取到有效文字，无法出题。")
        return

    print("\n文件读取成功！")

    print(f"提取字符数量：{len(material)}")

    # 保存提取的原始文字
    text_path = BASE_DIR / "extracted_text.txt"

    text_path.write_text(
        material,
        encoding="utf-8"
    )

    print("\n文字已保存到：")
    print(text_path)

    # 展示部分识别结果
    print("\n========== 提取内容预览 ==========")

    print(material[:500])

    print("\n==================================")

    # 将文本分段
    parts = split_text(material)

    print(f"\n全文共分为{len(parts)}段")

    if len(parts) > MAX_PARTS:

        print(
            f"当前是测试模式，仅使用前{MAX_PARTS}段生成题目。"
        )

    selected_parts = parts[:MAX_PARTS]

    all_questions = []

    # 分段生成
    for index, part in enumerate(
        selected_parts,
        start=1
    ):

        print(
            f"\n正在处理第{index}/"
            f"{len(selected_parts)}段..."
        )

        questions = generate_questions(part)

        # 为题目添加来源
        for question in questions:

            question["sourceFile"] = file_path.name

            question["sourcePart"] = index

        all_questions.extend(questions)

        print(
            f"当前段生成{len(questions)}道有效结构题目"
        )

    if not all_questions:

        print("没有生成有效题目。")
        return

    # 最终输出
    result = {
        "sourceFile": file_path.name,
        "total": len(all_questions),
        "questions": all_questions
    }

    output_path = BASE_DIR / "questions.json"

    with open(
        output_path,
        "w",
        encoding="utf-8"
    ) as file:

        json.dump(
            result,
            file,
            ensure_ascii=False,
            indent=4
        )

    print("\n========== 生成完成 ==========")

    print(f"共生成{len(all_questions)}道题目")

    print("题目保存位置：")
    print(output_path)

    print("\n请人工检查题目、答案和知识点是否正确。")


# =====================================
# 10. 程序入口
# =====================================

if __name__ == "__main__":

    try:

        main()

    except Exception as error:

        print("\n程序执行失败：")

        print(
            type(error).__name__,
            str(error)
        )
