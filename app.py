import os
import re
import time
import calendar
from datetime import datetime, timezone, timedelta
from threading import Lock
from flask import Flask, render_template, jsonify, request
import requests

app = Flask(__name__)
AIRPORTS = {
 'RCTP':('桃園國際機場',25.0797,121.2342),'RCSS':('臺北松山機場',25.0694,121.5525),
 'RCMQ':('臺中國際機場',24.2647,120.6206),'RCKH':('高雄國際機場',22.5771,120.3500),
 'RCNN':('臺南機場',22.9504,120.2058),'RCYU':('花蓮機場',24.0231,121.6176),
 'RCFN':('臺東機場',22.7549,121.1017),'RCQC':('澎湖機場',23.5687,119.6283),
 'RCBS':('金門機場',24.4279,118.3592),'RCFG':('南竿機場',26.1598,119.9581),
 'RCMT':('北竿機場',26.2242,120.0025),'RCLY':('蘭嶼機場',22.0288,121.5351),
 'RCLM':('綠島機場',22.6739,121.4669)
}
TZ = timezone(timedelta(hours=8))
CACHE = {}
LOCK = Lock()
SESSION = requests.Session()
SESSION.headers.update({'User-Agent':'SchoolAviationWeatherDemo/1.0 (educational)'})
WIND = re.compile(r'^(\d{3}|VRB)(\d{2,3})(?:G(\d{2,3}))?KT$')
CLOUD = re.compile(r'^(FEW|SCT|BKN|OVC|VV)(\d{3})(CB|TCU)?$')
CHANGE = re.compile(r'^FM\d{6}$|^(?:TEMPO|BECMG|PROB30|PROB40)$')
WX = {'TSRA':'雷雨','+TSRA':'強雷雨','-TSRA':'輕雷雨','RA':'降雨','+RA':'強降雨','-RA':'小雨','SHRA':'陣雨','+SHRA':'強陣雨','FG':'霧','BR':'薄霧','HZ':'霾','SN':'降雪','VCTS':'附近雷暴','NSW':'無顯著天氣'}

def fetch(kind,icao):
    url=f'https://aviationweather.gov/api/data/{kind}'
    r=SESSION.get(url,params={'ids':icao,'format':'json'},timeout=12)
    if r.status_code==204 or not r.content.strip(): return None
    r.raise_for_status()
    data=r.json()
    return data[0] if isinstance(data,list) and data and isinstance(data[0],dict) else None

def raw_of(record,kind):
    for k in (('rawOb','rawMETAR','rawMetar','raw') if kind=='metar' else ('rawTAF','rawTaf','raw')):
        if isinstance((record or {}).get(k),str):return record[k].strip()
    return ''

def conditions(tokens):
    out={'wind':None,'visibility_m':None,'clouds':[],'weather':[],'cavok':False}
    for t in tokens:
        w=WIND.fullmatch(t)
        if w:
            out['wind']={'direction':w[1]+'°' if w[1]!='VRB' else '不定','degrees':int(w[1]) if w[1]!='VRB' else None,'speed_kt':int(w[2]),'gust_kt':int(w[3]) if w[3] else None}
        elif t=='CAVOK':
            out['cavok']=True;out['visibility_m']=10000
        elif re.fullmatch(r'\d{4}',t) and int(t)<=9999:
            out['visibility_m']=10000 if t=='9999' else int(t)
        else:
            c=CLOUD.fullmatch(t)
            if c:
                out['clouds'].append({'cover':c[1],'height_ft':int(c[2])*100,'type':c[3] or ''})
            elif t in WX:
                out['weather'].append(WX[t])
    return out

def flight_category(c):
    vis=c['visibility_m']
    ceilings=[v['height_ft'] for v in c['clouds'] if v['cover'] in ('BKN','OVC','VV')]
    ceiling=min(ceilings) if ceilings else None
    # FAA-style categories: visibility meters approximated from statute miles.
    if (vis is not None and vis<1609) or (ceiling is not None and ceiling<500):return 'LIFR'
    if (vis is not None and vis<4828) or (ceiling is not None and ceiling<1000):return 'IFR'
    if (vis is not None and vis<8047) or (ceiling is not None and ceiling<=3000):return 'MVFR'
    if vis is None:return '未知'
    return 'VFR'

def hazards(c):
    out=[];w=c['wind'] or {};vis=c['visibility_m']
    if w.get('speed_kt',0)>=25:out.append('強風')
    if (w.get('gust_kt') or 0)>=20:out.append('強陣風')
    if vis is not None and vis<5000:out.append('低能見度')
    if any(v['cover'] in ('BKN','OVC','VV') and v['height_ft']<=1000 for v in c['clouds']):out.append('低雲底')
    if any('雷' in v for v in c['weather']):out.append('雷暴')
    if any('強' in v for v in c['weather']):out.append('強降水')
    return out

def month_for_day(day,ref):
    choices=[]
    for shift in (-1,0,1):
        year=ref.year+(ref.month+shift-1)//12
        month=(ref.month+shift-1)%12+1
        if day<=calendar.monthrange(year,month)[1]:
            dt=datetime(year,month,day,tzinfo=timezone.utc)
            choices.append(dt)
    return min(choices,key=lambda d:abs((d-ref).total_seconds())) if choices else None

def local_window(value,ref):
    a,b=value.split('/')
    if len(a)!=4 or len(b)!=4:return value
    def parse(v):
        d,h=int(v[:2]),int(v[2:])
        base=month_for_day(d,ref)
        if not base:return None
        return base+timedelta(hours=h)
    start,end=parse(a),parse(b)
    if not start or not end:return value
    if end<=start:
        # choose next month for end if period spans month boundary
        y=start.year+(start.month//12);m=start.month%12+1
        if int(b[:2])<=calendar.monthrange(y,m)[1]:end=datetime(y,m,int(b[:2]),tzinfo=timezone.utc)+timedelta(hours=int(b[2:]))
    fmt=lambda d:d.astimezone(TZ).strftime('%m/%d %H:%M')
    return f'{fmt(start)} ～ {fmt(end)}（台灣時間）'

def taf_groups(raw,ref):
    tokens=raw.replace('\n',' ').replace('=',' ').split()
    window=next((t for t in tokens[:9] if re.fullmatch(r'\d{4}/\d{4}',t)),None)
    groups=[{'title':'基本預報','tokens':[]}]
    i=0
    while i<len(tokens):
        t=tokens[i]
        if CHANGE.fullmatch(t):
            title={'TEMPO':'暫時變化','BECMG':'逐漸轉變','PROB30':'機率30%','PROB40':'機率40%'}.get(t,t)
            if t.startswith('FM'):
                base=month_for_day(int(t[2:4]),ref)
                if base:
                    dt=base+timedelta(hours=int(t[4:6]),minutes=int(t[6:8]))
                    title='FM 從 '+dt.astimezone(TZ).strftime('%m/%d %H:%M')+'（台灣時間）起'
            if t.startswith('PROB') and i+1<len(tokens) and tokens[i+1]=='TEMPO':
                title+=' 暫時變化';i+=1
            if i+1<len(tokens) and re.fullmatch(r'\d{4}/\d{4}',tokens[i+1]):
                i+=1;title+='：'+local_window(tokens[i],ref)
            groups.append({'title':title,'tokens':[]})
        else:groups[-1]['tokens'].append(t)
        i+=1
    return {'validity':local_window(window,ref) if window else '未提供','groups':[{'title':g['title'],'conditions':conditions(g['tokens']),'hazards':hazards(conditions(g['tokens']))} for g in groups if g['tokens']]}

def summary(m,t):
    if not m:return '目前無可用 METAR；無法判斷即時飛行條件。'
    c=m['conditions'];w=c['wind'];parts=[f"目前飛行條件分類為 {m['category']}（美國式分類）。"]
    if w:parts.append(f"風向 {w['direction']}，風速 {w['speed_kt']} 節。")
    if c['visibility_m'] is not None:parts.append('能見度至少 10 公里。' if c['visibility_m']>=10000 else f"能見度 {c['visibility_m']} 公尺。")
    parts.append('已辨識警示：'+('、'.join(m['hazards']) if m['hazards'] else '未觸發設定門檻')+'。')
    winds=[(g['conditions']['wind'] or {}).get('direction') for g in (t or {}).get('groups',[])]
    winds=[w for w in winds if w]
    if len(set(winds))>1:parts.append('TAF 包含多個不同風向的預報段落，請留意風向變化。')
    parts.append('本摘要為規則式教學資訊，並非 AI 模型生成或飛航決策建議。')
    return ' '.join(parts)

@app.get('/')
def index():return render_template('index.html')

@app.get('/api/airports')
def airports():return jsonify([{'icao':k,'name':v[0],'lat':v[1],'lon':v[2]} for k,v in AIRPORTS.items()])

@app.get('/api/weather/<icao>')
def weather(icao):
    icao=icao.upper()
    if icao not in AIRPORTS:return jsonify({'error':'僅支援清單內的台灣機場'}),400
    with LOCK:
        cached=CACHE.get(icao)
        if cached and time.time()-cached[0]<120:return jsonify(cached[1])
    try:
        mr=fetch('metar',icao);tr=fetch('taf',icao)
        mr_raw=raw_of(mr,'metar');tr_raw=raw_of(tr,'taf')
        m=None
        if mr_raw:
            c=conditions(mr_raw.replace('=',' ').split())
            m={'raw':mr_raw,'conditions':c,'category':flight_category(c),'hazards':hazards(c)}
        ref=datetime.now(timezone.utc)
        if tr and tr.get('issueTime'):
            try:ref=datetime.fromtimestamp(int(tr['issueTime']),timezone.utc)
            except (ValueError,TypeError,OverflowError):pass
        t=taf_groups(tr_raw,ref) if tr_raw else None
        if t:t['raw']=tr_raw
        result={'icao':icao,'name':AIRPORTS[icao][0],'metar':m,'taf':t,'summary':summary(m,t),'fetched_at':datetime.now(TZ).isoformat()}
        with LOCK:CACHE[icao]=(time.time(),result)
        return jsonify(result)
    except (requests.RequestException,ValueError) as e:
        app.logger.warning('weather fetch error %s: %s',icao,e)
        return jsonify({'error':'氣象服務暫時無法取得資料，請稍後重試'}),503

@app.get('/health')
def health():return jsonify({'status':'ok'})

if __name__=='__main__':
    app.run(host='127.0.0.1',port=int(os.getenv('PORT','5000')),debug=False)
