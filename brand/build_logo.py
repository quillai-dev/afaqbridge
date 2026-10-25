"""Builds the AfaqBridge brand SVGs. Wordmark is converted to outlines (Poppins, SIL OFL) so no font is needed."""
from fontTools.ttLib import TTFont
from fontTools.pens.svgPathPen import SVGPathPen
from fontTools.pens.transformPen import TransformPen
import os
F=os.environ.get('POPPINS_DIR','/tmp/fonts/node_modules/@fontsource/poppins/files/')
NAVY='#102A43'; TEAL='#20B8A6'; WHITE='#FFFFFF'

def text_path(text, font_file, size, x0, y0, tracking=0, kern=None):
    f=TTFont(F+font_file); gs=f.getGlyphSet(); cmap=f.getBestCmap(); upm=f['head'].unitsPerEm
    sc=size/upm; x=x0; d=[]
    for i,ch in enumerate(text):
        g=cmap[ord(ch)]; pen=SVGPathPen(gs)
        tp=TransformPen(pen,(sc,0,0,-sc,x,y0)); gs[g].draw(tp)
        d.append(pen.getCommands())
        x+=gs[g].width*sc+tracking+(kern or {}).get(text[i:i+2],0)
    return ' '.join(d), x

# ---- symbol, 64x64. Pointed arch (bridge span / doorway / letter A) crossed by a turquoise deck-horizon that
# runs past both piers (the two sides being connected). The arch is cut where the deck passes (mask) so the
# turquoise bar reads as separate from the navy piers - works on any background, including transparent.
def symbol(arch, deck, mid, uid):
    return f'''<defs><mask id="gap{uid}" maskUnits="userSpaceOnUse" x="0" y="0" width="64" height="64">
<rect width="64" height="64" fill="#fff"/><rect x="0" y="34.5" width="64" height="11" fill="#000"/></mask></defs>
<path d="M14 56 C14 31 23 15 32 8 C41 15 50 31 50 56" fill="none" stroke="{arch}" stroke-width="7.5" stroke-linejoin="round" mask="url(#gap{uid})"/>
<rect x="3" y="37.5" width="58" height="5" rx="2.5" fill="{deck}"/>'''

def svg(w,h,body,title='AfaqBridge'):
    return f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" width="{w}" height="{h}" role="img" aria-label="{title}"><title>{title}</title>{body}</svg>\n'

def lockup(arch,deck,word,tag,uid):
    # symbol 64 -> scaled 1.5 => 96; wordmark to the right
    afaq,x1=text_path('Afaq','poppins-latin-600-normal.woff',58,0,0,tracking=-0.6)
    bridge,x2=text_path('Bridge','poppins-latin-500-normal.woff',58,x1+1.5,0,tracking=-0.6)
    W=int(112+x2)+8; H=120
    tagp,_=text_path('INTERNATIONAL APPLICATIONS & SERVICES','poppins-latin-500-normal.woff',10.4,0,0,tracking=2.2)
    body=f'<g transform="translate(4 12) scale(1.5)">{symbol(arch,deck,None,uid)}</g>'
    body+=f'<g transform="translate(112 66)" fill="{word}"><path d="{afaq}"/><path d="{bridge}"/></g>'
    if tag: body+=f'<g transform="translate(114 92)" fill="{word}" opacity=".78"><path d="{tagp}"/></g>'
    return svg(W,H,body)

out=os.environ.get('OUT','out'); os.makedirs(out,exist_ok=True)
w=lambda n,s: open(f'{out}/{n}','w').write(s)
w('afaqbridge-logo.svg', lockup(NAVY,TEAL,NAVY,True,'a'))                    # primary, transparent bg
w('afaqbridge-logo-mono.svg', lockup(NAVY,NAVY,NAVY,True,'b'))                # monochrome
rev=lockup(WHITE,TEAL,WHITE,True,'c'); w('afaqbridge-logo-reversed-transparent.svg',rev)
w('afaqbridge-logo-reversed.svg', rev.replace('><title>','><rect width="100%" height="100%" fill="'+NAVY+'"/><title>',1))
w('afaqbridge-icon.svg', svg(64,64,symbol(NAVY,TEAL,None,'d')))              # standalone symbol, transparent
w('afaqbridge-icon-mono.svg', svg(64,64,symbol(NAVY,NAVY,None,'e')))
# app icon / avatar / favicon: navy rounded square with the reversed symbol (readable on any tab colour)
fav=svg(64,64,f'<rect width="64" height="64" rx="14" fill="{NAVY}"/><g transform="translate(8 8) scale(.75)">{symbol(WHITE,TEAL,None,"f")}</g>')
w('favicon.svg',fav); w('afaqbridge-app-icon.svg',fav)
print(os.listdir(out))
