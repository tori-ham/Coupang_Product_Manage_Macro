import os
import sys
import time
import hmac, hashlib
import requests
from pathlib import Path

ENV_PATH = os.path.join(os.path.dirname(__file__), "environment.txt")

def get_base_dir():
    # PyInstaller onefile일 때 실행 파일 경로
    if getattr(sys, 'frozen', False):
        return Path(sys.executable).parent
    # 스크립트로 실행할 때는 소스 파일 기준
    return Path(__file__).resolve().parent

BASE_DIR = get_base_dir()
ENV_PATH = BASE_DIR / "environment.txt"

def _parse_bool(v, default=False):
    if v is None:
        return default
    return str(v).strip().lower() in ("1","true","t","yes","y","on")

def _parse_int(v, default):
    try:
        return int(str(v).strip())
    except:
        return default

def load_env_from_file(path=ENV_PATH):
    env = {}
    if not os.path.exists(path):
        sample = (
            "ACCESS_KEY=\n"
            "SECRET_KEY=\n"
            "SELLER_ID=\n"
            "PRODUCT_COUNT=3\n"
            "SLEEP_INTERVAL=300\n"
            "LOG_MUTE=false\n"
        )
        with open(path, "w", encoding="utf-8") as f:
            f.write(sample)

    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            s = line.strip()
            if not s or s.startswith("#"):
                continue
            if "=" not in s:
                continue
            k, v = s.split("=", 1)
            env[k.strip().upper()] = v.strip()
    return env

CFG = load_env_from_file()

os.environ['TZ'] = 'GMT+0'

accesskey = CFG.get("ACCESS_KEY", "")
secretkey = CFG.get("SECRET_KEY", "")
seller_id = CFG.get("SELLER_ID", "")

PRODUCT_COUNT = _parse_int(CFG.get("PRODUCT_COUNT"), 2)
SLEEP_INTERVAL = _parse_int(CFG.get("SLEEP_INTERVAL"), 180)
LOG_MUTE = _parse_bool(CFG.get("LOG_MUTE"), False)

datetime=time.strftime('%y%m%d')+'T'+time.strftime('%H%M%S')+'Z'
method = "GET"

# path = "/v2/providers/seller_api/apis/api/v1/marketplace/seller-products"
BASE= "https://api-gateway.coupang.com"
urls = {
    "list" : "/v2/providers/seller_api/apis/api/v1/marketplace/seller-products?vendorId="+seller_id+"&maxPerPage=100&status=APPROVED",
    "info" : "/v2/providers/seller_api/apis/api/v1/marketplace/seller-products/",
    "update" : "/v2/providers/seller_api/apis/api/v1/marketplace/vendor-items/"
}

def generateHmac(method, url, secretKey, accessKey):
    path, *query = url.split("?")
    os.environ["TZ"] = "GMT+0"
    datetime = time.strftime('%y%m%d')+'T'+time.strftime('%H%M%S')+'Z'
    message = datetime + method + path + (query[0] if query else "")

    signature = hmac.new(
        bytes(secretKey, "utf-8"),
        message.encode("utf-8"),
        hashlib.sha256
    ).hexdigest()

    return "CEA algorithm=HmacSHA256, access-key={}, signed-date={}, signature={}".format(accessKey, datetime, signature)

REQUEST_TIMEOUT= (5, 15)
def call_api(api_url, method, auth):
    # url = "https://api-gateway.coupang.com"+api_url
    url= BASE+api_url
    res= requests.request(
        method= method,
        url= url,
        headers= {
            "Authorization": auth,
            "Content-Type": "application/json"
        },
        timeout=REQUEST_TIMEOUT
    )
    res.raise_for_status()
    return res

def get_update_data(item_data):
    data= {}
    data["sellerProductId"]= item_data["sellerProductId"]
    data["displayCategoryCode"]= item_data["displayCategoryCode"]
    data["sellerProductName"]= item_data["sellerProductName"]
    data["vendorId"]= item_data["vendorId"]
    data["saleStartedAt"]= item_data["saleStartedAt"]
    data["saleEndedAt"]= item_data["saleEndedAt"]
    data["displayProductName"]= item_data["displayProductName"]
    data["brand"]= item_data["brand"]

def print_with_mute(msg="", *, force=False):
    if force or not LOG_MUTE:
        print(msg, flush=True)

def main_logic():
    print_with_mute(f"=== 실행 시작: {time.strftime('%Y-%m-%d %H:%M:%S')} ===")
    if not (accesskey and secretkey and seller_id):
        print_with_mute("[WARN] ACCESS_KEY/SECRET_KEY/SELLER_ID 중 일부가 비어있습니다. environment.txt를 확인하세요.", force=True)
    
    sig= generateHmac("GET", urls['list'], secretkey, accesskey)

    paging_next_token= None
    res= call_api(urls['list'], "GET", sig)
    data= res.json()
    
    if data['code'].lower() == "success":
        if len(data['nextToken']) > 0 :
            paging_next_token= data['nextToken']
        products= data['data']
        for productIndex, product in enumerate(products):
            productId= product['sellerProductId']
            productUrl= urls['info'] + str(productId)
            productSig= generateHmac("GET", productUrl, secretkey, accesskey)
            productRes= call_api(productUrl, "GET", productSig)
            print_with_mute("---------------------------------------")
            productJson= productRes.json()
            productName= productJson['data']['sellerProductName']
            productItems= productJson['data']['items']
            
            for productItemIndex, productItem in enumerate(productItems):
                print_with_mute("상품명 : " + productName)
                print_with_mute("옵션 : " + productItem['itemName'])
                print_with_mute("현재 재고 수량 : " + str(productItem['maximumBuyCount']))
                if productItem['maximumBuyCount'] < PRODUCT_COUNT:
                    updateUrl= urls['update'] + str(productItem['vendorItemId']) + "/quantities/" + str(PRODUCT_COUNT)
                    updateSig= generateHmac("PUT", updateUrl, secretkey, accesskey)
                    updateRes= call_api(updateUrl, "PUT", updateSig)
                    updateData= updateRes.json()
                    print_with_mute("** 상품 재고를 " + str(productItem['maximumBuyCount']) + "개에서 " + str(PRODUCT_COUNT) + "개로 변경합니다.")
                    print_with_mute(updateData)
                else:
                    print_with_mute("** 상품 재고를 변경하지 않습니다.")
                print_with_mute("---------------------------------------")
            print_with_mute()

if __name__ == "__main__":
    try:
        while True:
            try:
                main_logic()
            except requests.HTTPError as e:
                body = ""
                try: body = e.response.text
                except: pass
                print_with_mute(f"[ERR] HTTPError: {e} body={body}", force=True)
            except requests.RequestException as e:
                print_with_mute(f"[ERR] NetworkError: {e}", force=True)
            except Exception as e:
                print_with_mute(f"[ERR] Unhandled: {e}", force=True)

            time.sleep(SLEEP_INTERVAL)
    except KeyboardInterrupt:
        # Ctrl+C 눌렀을 때 깔끔 종료
        print_with_mute("\n[INFO] 사용자 중단으로 종료합니다.", force=True)