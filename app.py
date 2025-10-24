from flask import Flask, request, jsonify
import json
import requests
from urllib.parse import parse_qs
from typing import Dict, Any, List

app = Flask(__name__)

# 外部APIのURLを定数として定義
EXTERNAL_API_BASE_URL = "https://api-teal-omega.vercel.app/get_data"




# ... 既存の import 文の下に追加 ...

import re
from typing import Dict, Any, List, Optional

# ... (既存の get_latest_innertube_params 関数など) ...

# =================================================================
# 3. 新しいヘルパー関数: JSファイルから復号化ロジックを抽出 (New!)
# =================================================================

def get_decipher_logic(js_url: str) -> Optional[Dict[str, Any]]:
    """
    プレーヤーJSファイルをダウンロードし、署名復号化に必要な関数名とロジックを抽出する。
    """
    try:
        # 1. JSファイルをダウンロード
        print(f"🔄 JSファイルダウンロード中: {js_url}")
        response = requests.get(js_url)
        response.raise_for_status()
        js_code = response.text
        
        # 2. 復号化メイン関数の検索
        # 通常、署名関数は a.split("") のような形式で始まります。
        # 例: a=function(a){a=a.split("");b.yG(a,72);b.zV(a,3);return a.join("")}
        # このパターンを見つけ、呼び出し元のオブジェクト名 (ここでは 'b') を抽出します。
        
        # main_func_match = re.search(r'a\.split\(""\)\s*;\s*([a-zA-Z0-9$]+)\.[a-zA-Z0-9$]+\(a,\d+\)', js_code)
        # プレーヤーバージョンによってパターンが変わるため、最も確実な署名復号化関数の検索パターンを探します。
        
        # 'a=a.split("");' から始まり 'return a.join("")' で終わる関数を見つけます。
        # プレーヤーJSは常にアップデートされるため、この正規表現はあなたの base.js の内容に合わせて調整が必要です。
        
        # 💡 まずは最も一般的なパターンで関数本体を抽出
        main_func_match = re.search(r'(\w+)\.sig\|\|(\w+)\.sig=function\s*\(\s*a\s*\)\s*{\s*a\s*=\s*a\.split\(""\)\s*;(.*?)return\s+a\.join\(""\)\s*}', js_code, re.DOTALL)
        
        if not main_func_match:
            print("❌ 署名復号化のメイン関数パターンが見つかりませんでした。")
            return None

        # 抽出された関数本体のコード
        signature_operations_code = main_func_match.group(3).strip()
        # 署名ヘルパー関数が格納されているオブジェクト名 (例: 'b' や 'c')
        helper_object_name = re.search(r'([a-zA-Z0-9$]+)\.[a-zA-Z0-9$]+\(a,\d+\)', signature_operations_code)
        
        if not helper_object_name:
            print("❌ ヘルパー関数のオブジェクト名が見つかりませんでした。")
            return None
        
        helper_obj_name = helper_object_name.group(1)
        
        # 3. ヘルパー関数群のロジックを検索
        # 例: b={zV:function(a,b){a.splice(0,b)},yG:function(a,b){var c=a[0];a[0]=a[b%a.length];a[b%a.length]=c}}
        # ヘルパー関数は必ずオブジェクトとして定義されています。
        helper_func_match = re.search(r'var\s+'+re.escape(helper_obj_name)+r'={.*?};', js_code, re.DOTALL)
        
        if not helper_func_match:
            print(f"❌ ヘルパー関数オブジェクト '{helper_obj_name}' の定義が見つかりませんでした。")
            return None

        helper_func_body = helper_func_match.group(0)

        # 4. 復号化に必要な情報として返す
        return {
            "main_operations": signature_operations_code,
            "helper_object_name": helper_obj_name,
            "helper_func_body": helper_func_body,
            "status": "success"
        }

    except Exception as e:
        print(f"❌ JS解析エラー: {e}")
        return {"status": "error", "message": str(e)}

# ... (既存の fetch_video_data 関数など) ...





# =================================================================
# 1. ヘルパー関数: URL要素の抽出・整形
# =================================================================





def extract_stream_info(format_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    formatsまたはadaptiveFormatsから、ストリームURLの基本情報を抽出・整形する。
    """
    stream_info: Dict[str, Any] = {
        "itag": format_data.get("itag"),
        "mimeType": format_data.get("mimeType"),
        "qualityLabel": format_data.get("qualityLabel", format_data.get("quality")),
        "is_ciphered": False,
        "is_playable": False,
        "url": None,
        "s_cipher": None # 暗号化された署名 (s)
    }

    if "url" in format_data:
        # デサイファリングが不要なストリーム
        stream_info["url"] = format_data["url"]
        stream_info["is_playable"] = True

    elif "signatureCipher" in format_data:
        # デサイファリングが必要なストリーム
        stream_info["is_ciphered"] = True
        
        # signatureCipherをパース
        cipher_params = parse_qs(format_data["signatureCipher"])
        
        # ベースURL ('url') の抽出とデコード
        base_url = cipher_params.get("url", [None])[0]
        if base_url:
            stream_info["url"] = base_url
            
        # 暗号化された署名 ('s') の抽出
        stream_info["s_cipher"] = cipher_params.get("s", [None])[0]
        
        # 署名パラメータ名 ('sp') の抽出
        stream_info["sp"] = cipher_params.get("sp", ["sig"])[0]

    # メタデータも追加
    stream_info["container"] = stream_info["mimeType"].split(";")[0].split("/")[-1]
    stream_info["vcodec"] = format_data.get("vcodec")
    stream_info["acodec"] = format_data.get("acodec")

    return stream_info

# =================================================================
# 2. Flask ルート定義 (データ取得と整理)
# =================================================================

@app.route("/parse_innertube", methods=['GET'])
def parse_innertube_api():
    """
    /parse_innertube?id=<VIDEO_ID> で外部APIからデータを取得し整形する。
    """
    # 1. videoId をクエリパラメーターから取得
    video_id = request.args.get('id')
    
    if not video_id:
        return jsonify({"status": "error", "message": "Video ID (id) is required. Usage: /parse_innertube?id=dQw4w9WgXcQ"}), 400

    # 2. 外部APIから生JSONデータを取得
    target_url = f"{EXTERNAL_API_BASE_URL}?id={video_id}"
    
    try:
        # requestsで外部APIにアクセス (以前のsubprocess+curlの役割を外部APIに委譲)
        response = requests.get(target_url)
        response.raise_for_status() # HTTPステータスコードが4xx, 5xxの場合は例外発生
        innertube_response: Dict[str, Any] = response.json()
        
    except requests.exceptions.RequestException as e:
        return jsonify({"status": "error", "message": f"Failed to fetch data from external API: {e}"}), 502 # 502 Bad Gateway

    # 3. Innertubeレスポンスの処理
    
    # エラーチェック（外部APIがエラーを返した場合）
    if innertube_response.get("status") == "error" or innertube_response.get("playabilityStatus", {}).get("status") in ["LOGIN_REQUIRED", "UNPLAYABLE"]:
        return jsonify(innertube_response), 403 # 403 Forbidden/Login Required

    streaming_data = innertube_response.get("streamingData", {})
    
    all_formats: List[Dict[str, Any]] = []
    if "formats" in streaming_data:
        all_formats.extend(streaming_data["formats"])
    if "adaptiveFormats" in streaming_data:
        all_formats.extend(streaming_data["adaptiveFormats"])

    # 4. 各フォーマットを処理して整形
    stream_list: List[Dict[str, Any]] = []
    for fmt in all_formats:
        stream_info = extract_stream_info(fmt)
        stream_list.append(stream_info)

    # 5. 結果をJSONとして整形して返す
    return jsonify({
        "status": "success",
        "videoId": video_id,
        "videoTitle": innertube_response.get("videoDetails", {}).get("title"),
        "stream_count": len(stream_list),
        "streams": stream_list
    })

# =================================================================
# 3. アプリケーション実行
# =================================================================

if __name__ == "__main__":
    app.run(port=5001, debug=True)
