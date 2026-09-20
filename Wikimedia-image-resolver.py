import requests
import os
import certifi
import ssl

CATEGORY = "Category:Katrina_Kaif"
API_URL = "https://commons.wikimedia.org/w/api.php"
HEADERS = {"User-Agent": "WikiImageBot/1.0 (Educational Use)"}

def get_session():
    """Create session that uses proper CA bundle and handles corporate proxy"""
    session = requests.Session()
    # Try to use certifi's bundle explicitly
    try:
        # This is the fix for most Windows installs
        session.verify = certifi.where()
    except:
        session.verify = True
    return session

def get_commons_images(session, category, limit=10):
    params = {
        "action": "query",
        "list": "categorymembers",
        "cmtitle": category,
        "cmtype": "file",
        "cmlimit": limit,
        "format": "json"
    }
    r = session.get(API_URL, params=params, headers=HEADERS, timeout=30)
    r.raise_for_status()
    data = r.json()
    return [m["title"] for m in data["query"]["categorymembers"]]

def get_image_info(session, file_title):
    params = {
        "action": "query",
        "titles": file_title,
        "prop": "imageinfo",
        "iiprop": "url|extmetadata|user",
        "iilimit": "1",
        "format": "json"
    }
    r = session.get(API_URL, params=params, headers=HEADERS, timeout=30)
    r.raise_for_status()
    pages = r.json()["query"]["pages"]
    page = next(iter(pages.values()))
    if "imageinfo" not in page:
        return None
    info = page["imageinfo"][0]
    license_name = info.get("extmetadata", {}).get("LicenseShortName", {}).get("value", "Unknown")
    return {
        "title": file_title,
        "url": info["url"],
        "license": license_name,
        "author": info.get("user"),
        "description_url": info.get("descriptionurl")
    }

if __name__ == "__main__":
    print("Searching Wikimedia Commons for Katrina Kaif...")
    print(f"Using CA bundle: {certifi.where()}")
    
    session = get_session()
    
    try:
        files = get_commons_images(session, CATEGORY, limit=15)
    except requests.exceptions.SSLError as e:
        print("\n--- SSL Error detected ---")
        print("Your network is injecting a self-signed cert (common on office laptops).")
        print("Trying insecure fallback for testing... (not recommended for production)")
        print(e)
        # LAST RESORT for testing only - bypass verification
        session.verify = False
        import urllib3
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
        files = get_commons_images(session, CATEGORY, limit=15)

    print(f"Found {len(files)} files")

    for f in files:
        info = get_image_info(session, f)
        if not info:
            continue
        print(f"\n{info['title']} - License: {info['license']}")
        if "CC" in info["license"] or "Public" in info["license"] or "PD" in info["license"]:
            safe_name = f.replace("File:", "").replace(" ", "_")
            print(f"Downloading {safe_name} ...")
            img = session.get(info["url"], headers=HEADERS, timeout=60)
            with open(safe_name, "wb") as out:
                out.write(img.content)
            print(f"Saved -> {safe_name}")
            print(f"Attribution: {info['author']} / {info['license']}")
            break
