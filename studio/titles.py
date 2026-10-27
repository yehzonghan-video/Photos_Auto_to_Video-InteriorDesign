"""共用影片標題的明確關聯；既有封面／正文欄位繼續負責渲染與樣式。"""
import re
from .models import number

BGM_API_VERSION=10
COVER_ID='project-cover-title'
BODY_ID='project-body-title'
DEFAULT_Y=(240+273+146)/1920


def display(text,breaks):
    points=set(breaks)
    return ''.join(('\n' if i in points else '')+c for i,c in enumerate(text))


def validate_link(raw,cover,body):
    if not isinstance(raw,dict) or type(raw.get('version')) is not int or raw.get('version')!=1 or raw.get('cover_id')!=COVER_ID or raw.get('body_id')!=BODY_ID:
        raise ValueError('標題關聯不正確，請重新確認封面與正文元素。')
    text=raw.get('text')
    if not isinstance(text,str) or len(text)>80 or '\n' in text or '\r' in text:raise ValueError('共用標題最多80字，換行請分別設定。')
    result=dict(version=1,cover_id=COVER_ID,body_id=BODY_ID,text=text,
                cover_x=number(raw.get('cover_x',.5),0,1),cover_y=number(raw.get('cover_y',DEFAULT_Y),0,1))
    for side,style in [('cover',cover),('body',body)]:
        breaks=raw.get(side+'_breaks',[])
        if not isinstance(breaks,list) or len(breaks)>5 or any(type(i) is not int or not 0<i<len(text) for i in breaks) or breaks!=sorted(set(breaks)):
            raise ValueError('標題換行位置不正確，最多6行。')
        if style['title']!=display(text,breaks):raise ValueError('封面與正文須使用同一個影片標題；請重新同步。')
        result[side+'_breaks']=list(breaks)
    if body['follow_cover']:raise ValueError('共用文字模式的封面與正文樣式需獨立保存。')
    return result


def project_title(cover):
    return (cover.get('shared_title') or {}).get('text',cover.get('title',''))


def filename(title,extension):
    if extension not in ('mp4','zip'):raise ValueError('檔案格式不正確。')
    clean=re.sub(r'[<>:"/\\|?*\x00-\x1f\x7f？]','',str(title))
    clean=re.sub(r'\s+',' ',clean).strip(' .')[:60].rstrip(' .')
    if not clean:clean='室內設計案例'
    if re.match(r'^(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\.|$)',clean,re.I):clean='案例_'+clean
    return clean+'.'+extension


def normalized_link(raw):
    """跨語言版本文件只納入明確關聯，不讓進入模式改變舊專案版本。"""
    return {k:raw[k] for k in ('version','cover_id','body_id','text','cover_x','cover_y','cover_breaks','body_breaks')}
