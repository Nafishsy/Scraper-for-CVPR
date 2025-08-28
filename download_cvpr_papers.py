import requests, os, re, time, json, argparse
from bs4 import BeautifulSoup
from urllib.parse import urljoin
from pathlib import Path

# quick filename cleanup
def fix_name(txt):
    txt = re.sub(r'[<>:"/\\|?*]', '', txt)  
    txt = re.sub(r'\s+', ' ', txt).strip()
    return txt[:200]  

def is_pdf(filepath):
    """Check if file is actually a PDF"""
    try:
        with open(filepath, 'rb') as f:
            header = f.read(4)
            return header == b'%PDF'
    except:
        return False

def find_pdf_url(paper_url, session):
    """Visit paper page and find the PDF download link"""
    try:
        response = session.get(paper_url, timeout=30)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.content, 'html.parser')
        
        # Look for PDF links
        pdf_links = soup.find_all('a', href=re.compile(r'\.pdf$', re.IGNORECASE))
        
        for link in pdf_links:
            href = link.get('href')
            if href:
                return urljoin(paper_url, href)
        
        # Alternative: look for links with "pdf" text
        for link in soup.find_all('a'):
            if link.get_text().strip().lower() == 'pdf':
                href = link.get('href')
                if href:
                    return urljoin(paper_url, href)
        
        return None
    except Exception as e:
        print(f"   error finding PDF: {e}")
        return None

def grab_file(url, path, session):
    try:
        r = session.get(url, stream=True, timeout=30)
        r.raise_for_status()
        
        # Check content type
        content_type = r.headers.get('content-type', '').lower()
        if 'pdf' not in content_type:
            print(f"   warning: content-type is '{content_type}'")
        
        total = int(r.headers.get('content-length', 0))
        done = 0
        
        with open(path, "wb") as f:
            for chunk in r.iter_content(8192):
                if not chunk: continue
                f.write(chunk)
                if total:
                    done += len(chunk)
                    pct = done * 100 / total
                    print(f"\r   ... {pct:.1f}%", end="")
        
        # Validate the downloaded file is actually a PDF
        if not is_pdf(path):
            print("\r   failed: not a valid PDF file")
            return False
            
        # Check file size is reasonable
        if path.stat().st_size < 1024:
            print("\r   failed: file too small")
            return False
            
        print("\r   ✓ downloaded")
        return True
    except Exception as e:
        print(f"   failed: {e}")
        return False

def load_log(logf):
    if logf.exists():
        try:
            return json.load(open(logf, "r", encoding="utf-8"))
        except:
            return {}
    return {}

def save_log(logf, data):
    with open(logf, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--retry-failed", action="store_true")
    ap.add_argument("--max-retries", type=int, default=3)
    args = ap.parse_args()

    base = "https://openaccess.thecvf.com/CVPR2024?day=2024-06-19"
    outdir = Path("cvpr_2024_papers")
    outdir.mkdir(exist_ok=True)

    flog = outdir / "failed.json"
    failed = load_log(flog)

    s = requests.Session()
    s.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.5",
        "Accept-Encoding": "gzip, deflate",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1",
    })

    # if retrying failed
    if args.retry_failed and failed:
        todo = list(failed.items())
        print(f"Retrying {len(todo)} failed downloads...")
    else:
        print("Fetching paper list...")
        try:
            r = s.get(base, timeout=60)
            r.raise_for_status()
        except Exception as e:
            print("Could not fetch main page:", e)
            return
        
        soup = BeautifulSoup(r.content, "html.parser")
        dt_elements = soup.select("#content > dl > dt")
        print(f"Found {len(dt_elements)} papers")

        todo = []
        for dt in dt_elements:
            title_link = dt.find("a")
            if not title_link: 
                continue
            
            title = title_link.get_text().strip()
            paper_page_url = urljoin(base, title_link.get("href"))
            
            # Store paper page URL, we'll find PDF URL later
            todo.append((title, paper_page_url))

    done, bad = 0, 0
    new_failed = {}

    for i, (title, paper_page_url) in enumerate(todo, 1):
        print(f"\n{i}/{len(todo)} {title}")
        fname = outdir / (fix_name(title) + ".pdf")

        if fname.exists() and fname.stat().st_size > 1024 and is_pdf(fname):
            print("   ✓ already exists (valid PDF)")
            failed.pop(title, None)
            continue

        # If retrying failed, use stored PDF URL, otherwise find it
        if args.retry_failed and title in failed:
            pdf_url = failed[title]
            print(f"   → using stored PDF URL")
        else:
            print(f"   → finding PDF link...")
            pdf_url = find_pdf_url(paper_page_url, s)
            if not pdf_url:
                print("   ✗ no PDF link found")
                bad += 1
                new_failed[title] = paper_page_url  # Store paper page for retry
                continue

        print(f"   → downloading PDF...")
        success = False
        for attempt in range(args.max_retries):
            if attempt: 
                print(f"   → retry {attempt+1}/{args.max_retries}")
                time.sleep(2)
            
            if grab_file(pdf_url, fname, s):
                done += 1
                failed.pop(title, None)
                success = True
                break
            else:
                if fname.exists(): 
                    fname.unlink()

        if not success:
            bad += 1
            new_failed[title] = pdf_url  # Store actual PDF URL for retry

        time.sleep(0.5)

    if new_failed or (args.retry_failed and failed):
        failed.update(new_failed)
        save_log(flog, failed)
    elif flog.exists():
        flog.unlink()

    print("\n==== SUMMARY ====")
    print("downloaded:", done)
    print("failed:", bad)
    print("saved in:", outdir.absolute())
    if bad:
        print("failed ones logged in:", flog)

if __name__ == "__main__":
    main()
