# md2html.py
# 将 README.md 按 "### hash: <hash>" 切分并按自定义标签生成 HTML
# 用法: python md2html.py [README.md] [output.html]

import sys
import re
import json
import html
from pathlib import Path

INPUT = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("README.md")
OUTPUT = Path(sys.argv[2]) if len(sys.argv) > 2 else Path("index.html")

# ---------- 辅助函数 ----------
def escape(s):
    return html.escape(s)

def red_replace(text):
    # 把 [red+]... [red-] 替换为 <span class="red">...</span>
    return re.sub(r'\[red\+\](.*?)\[red-\]', lambda m: f'<span class="red">{escape(m.group(1))}</span>', text, flags=re.S)

def paragraphize(text):
    # 去除首尾空行，按两个及以上换行分段
    lines = text.strip().splitlines()
    if not lines:
        return []
    # 合并连续非空行为同一段，保留单个换行为换行符 (但是这里简单处理为 <br/>)
    paragraphs = []
    cur = []
    for ln in lines:
        if ln.strip() == '':
            if cur:
                paragraphs.append(' '.join(cur))
                cur = []
            else:
                # 连续空行 -> 忽略（段落已经切分）
                pass
        else:
            cur.append(ln.rstrip())
    if cur:
        paragraphs.append(' '.join(cur))
    return paragraphs

def render_paragraphs(text):
    # 先处理 [red+], 再分成段落
    text = red_replace(text)
    paras = paragraphize(text)
    return '\n'.join(f'<p>{p}</p>' for p in paras)

# ---------- 解析单个区块内的自定义标签 ----------
# 标签格式大致为: [Smain]...[-], [main]...[-], [subtitle1]...[-], [subtitle2]...[-]
# 还有 [bannerT2]{json}[-] 和 [cardT]{json}[-]

def find_tag_blocks(section_text):
    """
    解析一个 hash 区块中的顶层标签序列。
    返回一个按顺序的元素列表，每个元素为 dict:
      { "type": tagname, "content": content_string }
    未匹配到任何标签的文本也会作为 {type: "text", content: "..."}
    """
    res = []
    s = section_text
    idx = 0
    # 通用匹配： [tagName] ... [-]
    tag_pattern = re.compile(r'\[([A-Za-z0-9_+-]+)\]', re.S)
    while idx < len(s):
        m = tag_pattern.search(s, idx)
        if not m:
            # 剩下全部作为普通文本
            tail = s[idx:].strip()
            if tail:
                res.append({"type":"text","content": tail})
            break
        tag = m.group(1)
        start = m.start()
        # add any text before tag
        if start > idx:
            before = s[idx:start].strip()
            if before:
                res.append({"type":"text","content": before})
        # find the closing delimiter "[-]" after the tag (special-case JSON inside some tags)
        close_pat = re.compile(r'\[-\]')
        cm = close_pat.search(s, m.end())
        if not cm:
            # 没有找到关闭标志，取到文件末尾
            content = s[m.end():].strip()
            idx = len(s)
        else:
            content = s[m.end():cm.start()].strip()
            idx = cm.end()
        res.append({"type": tag, "content": content})
    return res

def render_bannerT2(json_text):
    try:
        obj = json.loads(json_text)
    except Exception as e:
        # 容错：把原文本输出为段落
        return f'<div class="error">Invalid bannerT2 JSON: {escape(json_text)}</div>'
    # 预期字段 img1.path, img2.path, txt1, txt2
    img1 = obj.get("img1", {}) or {}
    img2 = obj.get("img2", {}) or {}
    p1 = img1.get("path","")
    p2 = img2.get("path","")
    t1 = obj.get("txt1","")
    t2 = obj.get("txt2","")
    return f'''
<div class="bannerT2">
  <div class="banner-item">
    <img src="{escape(p1)}" alt="{escape(t1)}"/>
    <div class="caption">{escape(t1)}</div>
  </div>
  <div class="banner-item">
    <img src="{escape(p2)}" alt="{escape(t2)}"/>
    <div class="caption">{escape(t2)}</div>
  </div>
</div>
'''.strip()

def render_cardT(json_text):
    try:
        obj = json.loads(json_text)
    except Exception as e:
        return f'<div class="error">Invalid cardT JSON: {escape(json_text)}</div>'
    img = obj.get("img", {}) or {}
    p = img.get("path","")
    txt = obj.get("txt","")
    return f'''
<div class="cardT">
  <div class="card-img"><img src="{escape(p)}" alt="{escape(txt)}"/></div>
  <div class="card-txt">{escape(txt)}</div>
</div>
'''.strip()

def render_tag_sequence(tag_seq):
    """
    tag_seq: list of {"type":..., "content":...}
    输出 HTML 字符串
    """
    out = []
    for node in tag_seq:
        t = node["type"]
        c = node["content"].strip()
        if t.lower() == "smain":
            # 次一级分隔（视作 h2）
            inner = render_paragraphs(c)
            # 如果 smain 内容本身也包含子标记（如 subtitle1 等），递归解析
            sub = find_tag_blocks(c)
            if any(x['type'].lower() in ("subtitle1","subtitle2","main","bannerT2","cardT") for x in sub):
                # 如果存在子标签，渲染为 container：h2 标题（如果纯文本）
                # 如果 smain 内容的开头有一行纯文本（比如 "9月25日更新"），使用它作为标题
                first_text = ""
                # 查找第一个纯文本作为 h2
                for x in sub:
                    if x['type'] == 'text':
                        first_text = x['content'].strip().splitlines()[0]
                        break
                if first_text:
                    out.append(f'<div class="smain"><h2>{escape(first_text)}</h2>')
                else:
                    out.append('<div class="smain">')
                # render children
                for x in sub:
                    if x['type'] == 'text':
                        # 如果是文本，放段落
                        out.append(render_paragraphs(x['content']))
                    elif x['type'].lower() == 'subtitle1':
                        # 第三级标题
                        out.append(f'<h3>{x["content"]}</h3>')
                    elif x['type'].lower() == 'subtitle2':
                        out.append(f'<h4>{x["content"]}</h4>')
                    elif x['type'] == 'bannerT2':
                        out.append(render_bannerT2(x['content']))
                    elif x['type'] == 'cardT':
                        out.append(render_cardT(x['content']))
                    elif x['type'].lower() == 'main':
                        # 嵌套 main，作为次级小标题
                        out.append(f'<div class="main"><h2>{x["content"]}</h2></div>')
                    else:
                        out.append(render_paragraphs(x['content']))
                out.append('</div>')  # close smain
            else:
                # 没有子标签，直接把内容当作一个 h2 + 段落
                content = escape(re.sub(r"\\s+", " ", c))
                out.append(f'<div class="smain"><h2>{content}</h2></div>')
        elif t.lower() == "main":
            # 次一级分隔 (视作 h2/h3) 这里用 h2
            # content 可能包含 red 标签
            html_c = red_replace(c)
            # 如果 content 里本身可能是多行文本，直接段落化
            out.append(f'<div class="main"><h2>{html_c}</h2></div>')
        elif t.lower() == "subtitle1":
            out.append(f'<h3>{c}</h3>')
        elif t.lower() == "subtitle2":
            out.append(f'<h4>{c}</h4>')
        elif t == "bannerT2":
            out.append(render_bannerT2(c))
        elif t == "cardT":
            out.append(render_cardT(c))
        elif t == "text":
            out.append(render_paragraphs(c))
        else:
            # 未知标签：尽量原样输出 content
            out.append(render_paragraphs(f'[{t}]' + c + '[-]'))
    return '\n'.join(out)

# ---------- 主流程 ----------
def split_by_hash_blocks(md_text):
    """
    按行查找 '### hash: <hash>'，把文件切分成多个区块。
    返回列表 [ { 'hash': hash, 'body': text_after_header_until_next_header } , ... ]
    如果文件开头在第一个 header 之前有内容，会作为 hash=None 的第一个区块（通常忽略）
    """
    pattern = re.compile(r'^\s*###\s*hash:\s*(\S+)\s*$', re.M)
    blocks = []
    last_pos = 0
    last_hash = None
    matches = list(pattern.finditer(md_text))
    if not matches:
        # 整个文档作为一个无 hash 块
        return [{"hash": None, "body": md_text}]
    for i, m in enumerate(matches):
        if i == 0 and m.start() > 0:
            pre = md_text[:m.start()].strip()
            if pre:
                blocks.append({"hash": None, "body": pre})
        h = m.group(1)
        h = h[:7]
        start_body = m.end()
        end_body = matches[i+1].start() if i+1 < len(matches) else len(md_text)
        body = md_text[start_body:end_body].strip()
        blocks.append({"hash": h, "body": body})
    return blocks[1:][::-1]

def build_html(md_text, title="Converted README"):
    blocks = split_by_hash_blocks(md_text)
    body_html_parts = []
    for blk in blocks:
        h = blk["hash"]
        b = blk["body"]
        # 1️⃣ 先全局替换 red 标签
        b = red_replace(b)

        if h is None:
            body_html_parts.append(f'<section class="no-hash">{render_paragraphs(b)}</section>')
            continue
        
        # 2️⃣ 再解析标签
        tags = find_tag_blocks(b)
        content_html = render_tag_sequence(tags)
        body_html_parts.append(f'<section id="{escape(h)}" class="hash-block"><h1>hash: {escape(h)}</h1>{content_html}</section>')
        
    body_html = '\n'.join(body_html_parts)
    # 基本 CSS
    css = '''
body { font-family: system-ui, -apple-system, "Segoe UI", Roboto, "Helvetica Neue", Arial; line-height:1.6; padding:20px; color:#222; background:#fff; }
main { max-width: 700px; margin: 0 auto; padding: 0 20px; }
h1, h2, h3 { text-align: center; }
h1 { border-bottom:2px solid #ddd; padding-bottom:6px; }
h2 { color:#2c3e50; margin-top:29px; margin-bottom:5px; }
h3 { color:#34495e; margin-top:23px; margin-bottom:5px; }
h4 { color:#4b6584; margin-top:20px; margin-bottom:5px; }
p { margin:8px 0; white-space:normal; }
.red { color: #c00; font-weight:600; }
.bannerT2 { display:flex; gap:12px; margin:12px 0; flex-wrap:wrap; background-color:antiquewhite; padding-top: 10px; padding-bottom:5px; }
.banner-item { flex:1 1 45%; text-align:center; }
.banner-item img { max-width:100%; height:auto; display:block; margin:0 auto; border-radius:6px; }
.banner-item .caption { margin-top:6px; font-size:0.95em; color:#555; }
.cardT { display:flex; gap:12px; align-items:center; margin:12px 0; background-color:aliceblue; }
.cardT .card-img img { max-width:220px; height:auto; border-radius:6px; display:block; }
.cardT .card-txt { flex:1; font-size:1.05em; color:#333; display:flex; align-items:center; justify-content:center; }
.hash-block { margin:28px 0; padding:10px 12px; border-radius:8px; box-shadow: 0 1px 0 rgba(0,0,0,0.03); }
.no-hash { margin:6px 0; }
.error { color:#900; background:#fee; padding:8px; border-radius:6px; }
@media (max-width:800px){
  .banner-item { flex:1 1 100%; }
  .cardT { flex-direction:column; align-items:flex-start; }
  .cardT .card-img img { max-width:100%; }
}
'''
    html_doc = f'''<!doctype html>
<html lang="zh">
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width,initial-scale=1"/>
  <title>{escape(title)}</title>
  <style>{css}</style>
</head>
<body>
  <main>
    <h0 style="display:none;">{escape(title)}</h0>
    {body_html}
  </main>
</body>
</html>
'''
    return html_doc

def main():
    if not INPUT.exists():
        print(f"输入文件不存在: {INPUT}", file=sys.stderr)
        sys.exit(2)
    md_text = INPUT.read_text(encoding='utf-8')
    html_out = build_html(md_text, title=INPUT.name)
    OUTPUT.write_text(html_out, encoding='utf-8')
    print(f"已生成 {OUTPUT} （来自 {INPUT}）")

if __name__ == "__main__":
    main()
