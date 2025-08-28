import requests, os, re, time, json, argparse
from bs4 import BeautifulSoup
from urllib.parse import urljoin
from pathlib import Path

# quick filename cleanup
def fix_name(txt):
    txt = re.sub(r'[<>:"/\\|?*]', '', txt)  
    txt = re.sub(r'\s+', ' ', txt).strip()
    return txt[:200]  

def grab_file(url, path, session):
    try:
        r = session.get(url, stream=True, timeout=30)
        r.raise_for_status()
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
        print("\r   ok")
        return True
    except Exception as e:
        print("   failed:", e)
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
    s.headers.update({"User-Agent": "Mozilla/5.0"})

    # if retrying failed
    if args.retry_failed and failed:
        todo = list(failed.items())
        print(f"Retrying {len(todo)} failed downloads...")
    else:
        print("Fetching index...")
        try:
            r = s.get(base, timeout=60)
            r.raise_for_status()
        except Exception as e:
            print("Could not fetch main page:", e)
            return
        soup = BeautifulSoup(r.content, "html.parser")
        titles = soup.select("#content > dl > dt")
        print("Found", len(titles), "papers")

        todo = []
        for t in titles:
            a = t.find("a")
            if not a: continue
            title = a.get_text().strip()
            dd = t.find_next_sibling("dd")
            if not dd: continue
            pdfa = dd.find("a")
            if not pdfa: continue
            url = urljoin(base, pdfa.get("href"))
            todo.append((title, url))

    done, bad = 0, 0
    new_failed = {}

    for i, (title, url) in enumerate(todo, 1):
        print(f"\n{i}/{len(todo)} {title}")
        fname = outdir / (fix_name(title) + ".pdf")

        if fname.exists() and fname.stat().st_size > 0:
            print("   already exists")
            failed.pop(title, None)
            continue

        success = False
        for attempt in range(args.max_retries):
            if attempt: 
                print("   retry", attempt+1)
                time.sleep(2)
            if grab_file(url, fname, s):
                done += 1
                failed.pop(title, None)
                success = True
                break
            else:
                if fname.exists(): fname.unlink()

        if not success:
            bad += 1
            new_failed[title] = url

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
