"""真實 API 檢查：金鑰由環境變數或隱藏提示輸入，從不寫檔或印出原始例外。"""
import argparse
import getpass
import json
import os
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from studio.ai import AIError, DEFAULT_MODEL, analyze_batch, client_for, safe_error
from studio.models import load_photo


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('images',nargs='+',type=Path)
    parser.add_argument('--model',default=DEFAULT_MODEL)
    parser.add_argument('--stdin-key',action='store_true',help='從 stdin 接收金鑰，不回顯')
    parser.add_argument('--list-models',action='store_true',help='列出官方 API 可用模型名稱及支援操作')
    args=parser.parse_args()
    key=os.environ.get('GEMINI_API_KEY') or (sys.stdin.readline().strip() if args.stdin_key else getpass.getpass('Gemini API key: '))
    try:
        with client_for(key) as client:
            if args.list_models:
                print(json.dumps({'real_api':True,'models':[
                    {'name':entry.name,'actions':entry.supported_actions}
                    for entry in client.models.list() if 'flash' in (entry.name or '')]},ensure_ascii=False))
            model=client.models.get(model=args.model)
            print(json.dumps({'real_api':True,'model_available':model.name},ensure_ascii=False))
    except Exception as exc:
        print(json.dumps({'real_api':True,'model_check':'failed','error':safe_error(exc)},ensure_ascii=False))
    photos=[load_photo(path.name,path.read_bytes()) for path in args.images]
    try:
        state={};reports=analyze_batch(photos,key,args.model,state)
        print(json.dumps({'real_api':True,'reports':reports,
            'results':{p.name:state.get('ai_results',{}).get(p.id,{}).get('items') for p in photos}},ensure_ascii=False))
        return 0 if all(r['ok'] for r in reports) else 1
    except AIError as exc:
        print(json.dumps({'real_api':True,'error':str(exc)},ensure_ascii=False));return 1


if __name__=='__main__':raise SystemExit(main())
