"""
모든 PDF → WebP 이미지 변환 → book/metadata.json 저장
GitHub Pages QR 코드 → qr.png 저장

실행: python generate_metadata.py
의존성: pip install pypdf pymupdf qrcode[pil] python-dotenv
설정:  .env 파일에서 DPI, 품질, URL 조정
"""

import json
import os
from pathlib import Path

from dotenv import load_dotenv
from pypdf import PdfReader
import fitz
from PIL import Image
import qrcode

load_dotenv()

SITE_URL          = os.getenv('SITE_URL',          'https://kwaho1993.github.io/2026_KSCLI/')
AD_RENDER_DPI     = int(os.getenv('AD_RENDER_DPI',     '150'))
AD_WEBP_QUALITY   = int(os.getenv('AD_WEBP_QUALITY',   '85'))
PAPER_RENDER_DPI  = int(os.getenv('PAPER_RENDER_DPI',  '150'))
PAPER_WEBP_QUALITY = int(os.getenv('PAPER_WEBP_QUALITY', '85'))

IMG_DIR   = Path('book/img')
DIR_ORDER   = {'cover': 0, 'ad': 1, 'papers': 2}
IMAGE_EXTS  = {'.png', '.jpg', '.jpeg'}
SOURCE_EXTS = {'.pdf'} | IMAGE_EXTS

# DIR_ORDER에 등록된 디렉터리만 스캔 → 빌드 산출물(img/, journal.pdf 등) 자동 제외
all_files = sorted(
    [p for p in Path('book').rglob('*')
     if p.suffix.lower() in SOURCE_EXTS and p.parent.name in DIR_ORDER],
    key=lambda p: (DIR_ORDER.get(p.parent.name, 99), p.name),
)

print(f'설정: 광고 {AD_RENDER_DPI}DPI/q{AD_WEBP_QUALITY}  논문 {PAPER_RENDER_DPI}DPI/q{PAPER_WEBP_QUALITY}')
print(f'      URL: {SITE_URL}')
print()

# ── 헬퍼 ─────────────────────────────────────────────────────────────────────

def get_page_ratios(path: Path) -> list[float]:
    reader = PdfReader(path)
    ratios = []
    for page in reader.pages:
        w = float(page.mediabox.width)
        h = float(page.mediabox.height)
        if page.rotation in (90, 270):
            w, h = h, w
        ratios.append(round(h / w, 6))
    return ratios

def render_to_webp(pdf_path: Path, out_dir: Path, dpi: int, quality: int) -> list[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    doc = fitz.open(str(pdf_path))
    paths = []
    for i in range(len(doc)):
        pix = doc[i].get_pixmap(matrix=fitz.Matrix(dpi / 72, dpi / 72), alpha=False)
        img = Image.frombytes('RGB', (pix.width, pix.height), pix.samples)
        out_path = out_dir / f"{pdf_path.stem}_p{i + 1}.webp"
        img.save(out_path, 'WEBP', quality=quality, method=6)
        paths.append(out_path)
    doc.close()
    return paths

# ── metadata.json ─────────────────────────────────────────────────────────────

def process_image(path: Path, out_dir: Path, quality: int) -> tuple[list[float], list[Path]]:
    """이미 이미지인 파일(PNG 등) → WebP 변환, 종횡비 반환."""
    out_dir.mkdir(parents=True, exist_ok=True)
    img = Image.open(path).convert('RGB')
    w, h = img.size
    out_path = out_dir / f"{path.stem}_p1.webp"
    img.save(out_path, 'WEBP', quality=quality, method=6)
    return [round(h / w, 6)], [out_path]

metadata = []
for path in all_files:
    is_cover = path.parent.name == 'cover'
    is_ad    = path.parent.name == 'ad'
    is_img   = path.suffix.lower() in IMAGE_EXTS

    dpi     = AD_RENDER_DPI    if is_ad else PAPER_RENDER_DPI
    quality = AD_WEBP_QUALITY  if is_ad else PAPER_WEBP_QUALITY
    tag     = 'cov' if is_cover else ('ad ' if is_ad else 'pdf')

    try:
        if is_img:
            ratios, img_paths = process_image(path, IMG_DIR, quality)
        else:
            ratios    = get_page_ratios(path)
            img_paths = render_to_webp(path, IMG_DIR, dpi, quality)

        pages    = [{"ratio": r, "img": p.as_posix()} for r, p in zip(ratios, img_paths)]
        total_kb = sum(p.stat().st_size for p in img_paths) // 1024
        print(f'  [{tag}] {path.name}  ({len(ratios)}p)  {total_kb}KB')
        metadata.append({"url": path.as_posix(), "pages": pages})
    except Exception as e:
        print(f'  FAIL  {path.name}: {e}')

out = Path('book/metadata.json')
out.write_text(json.dumps(metadata, ensure_ascii=False, separators=(',', ':')), encoding='utf-8')
print(f'\n→ {out}  ({out.stat().st_size:,} bytes)')

# ── 학술지 PDF 생성 (WebP 이미지 → PDF 재조립) ───────────────────────────────────

def create_journal_pdf(metadata, out_path: Path):
    import io
    doc = fitz.open()
    for item in metadata:
        for page_data in item['pages']:
            w_pts = 595
            h_pts = round(w_pts * page_data['ratio'])
            page = doc.new_page(width=w_pts, height=h_pts)
            # WebP → JPEG 변환 후 스트림으로 삽입 (pymupdf는 WebP 직접 지원 안 함)
            buf = io.BytesIO()
            Image.open(page_data['img']).save(buf, 'JPEG', quality=85)
            page.insert_image(fitz.Rect(0, 0, w_pts, h_pts), stream=buf.getvalue())
    doc.save(str(out_path), deflate=True, garbage=4)
    doc.close()

journal_path = Path('book/journal.pdf')
print('학술지 PDF 생성 중...')
create_journal_pdf(metadata, journal_path)
print(f'→ {journal_path}  ({journal_path.stat().st_size / (1024*1024):.1f} MB)')

# ── QR 코드 ───────────────────────────────────────────────────────────────────

qr = qrcode.QRCode(error_correction=qrcode.constants.ERROR_CORRECT_M, box_size=10, border=4)
qr.add_data(SITE_URL)
qr.make(fit=True)
qr.make_image(fill_color='black', back_color='white').save('qr.png')
print(f'→ qr.png  ({Path("qr.png").stat().st_size:,} bytes)  {SITE_URL}')
