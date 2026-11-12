import zipfile
from pathlib import Path
from .config import MAX_FILE_BYTES

SUPPORTED={'.pdf','.docx','.png','.jpg','.jpeg','.bmp','.webp','.txt'}
def validate_file(path: Path, name: str):
    suffix=Path(name).suffix.lower()
    if suffix not in SUPPORTED:raise ValueError('不支持此格式，请选择 PDF、DOCX、图片或 TXT')
    size=path.stat().st_size
    if not size:raise ValueError('文件为空（0 字节），请重新保存或选择原始文件')
    if size>MAX_FILE_BYTES:raise ValueError('单文件超过 20 MB')
    if suffix=='.docx':
        if not zipfile.is_zipfile(path):raise ValueError('DOCX 不是有效文档容器，可能已损坏、受保护或扩展名不正确')
        with zipfile.ZipFile(path) as z:
            if not {'[Content_Types].xml','word/document.xml'}<=set(z.namelist()):raise ValueError('DOCX 缺少正文结构')
            if sum(x.file_size for x in z.infolist())>80*1024*1024:raise ValueError('DOCX 解压内容超过限制')
    elif suffix=='.pdf':
        import pymupdf
        with pymupdf.open(path) as pdf:
            if pdf.needs_pass:raise ValueError('PDF 需要密码，请先导出未加密副本')
            if not len(pdf):raise ValueError('PDF 没有页面')
    elif suffix!='.txt':
        from PIL import Image
        with Image.open(path) as im:im.verify()
