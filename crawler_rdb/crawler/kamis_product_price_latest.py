import requests
import xml.etree.ElementTree as ET
import os
import json
from dotenv import load_dotenv

load_dotenv()

def crawl_kamis_product_price_latest():
    url = "https://www.kamis.or.kr/service/price/xml.do"
    params = {
        "action": "dailySalesList",
        "p_cert_key": os.getenv("KAMIS_API_KEY"),
        "p_cert_id": os.getenv("KAMIS_API_ID"),
        "p_returntype": "xml"
    }

    response = requests.get(url, params=params)
    response.raise_for_status()

    root = ET.fromstring(response.content)
    results = []
    for item in root.findall(".//item"):
        row = {elem.tag: elem.text for elem in item}
        results.append(row)

    return results  # JSON 호환 가능한 리스트[딕셔너리]
