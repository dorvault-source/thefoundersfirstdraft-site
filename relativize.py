import pathlib,re
root=pathlib.Path('.')
for f in root.rglob('*.html'):
    depth=len(f.relative_to(root).parts)-1
    pre='../'*depth
    s=f.read_text()
    def fix(m):
        attr,url=m.group(1),m.group(2)
        if url=='/': url='index.html'
        elif url.endswith('/'): url=url[1:]+'index.html'
        elif url=='/privacy': url='privacy/index.html'
        else: url=url[1:]
        return f'{attr}="{pre}{url}"'
    s=re.sub(r'(href|src)="(/(?!/)[^"]*)"',fix,s)
    f.write_text(s)
    print(f)
