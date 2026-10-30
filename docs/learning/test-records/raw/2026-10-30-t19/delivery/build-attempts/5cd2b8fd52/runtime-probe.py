import json, importlib.metadata as m
from rapidocr_onnxruntime import RapidOCR
from playwright.sync_api import sync_playwright
ocr=RapidOCR()
with sync_playwright() as p:
 b=p.chromium.launch(headless=True,args=['--no-sandbox'])
 page=b.new_page(); page.set_content('<html><body>ResuMate 中文字体</body></html>')
 pdf=page.pdf(); version=b.version; b.close()
print(json.dumps({'rapidocr_initialized':True,'chromium_launched':True,'chromium_version':version,'pdf_bytes':len(pdf),'versions':{name:m.version(name) for name in ['deepagents','langgraph','redis','rapidocr-onnxruntime','onnxruntime','playwright']}}))
