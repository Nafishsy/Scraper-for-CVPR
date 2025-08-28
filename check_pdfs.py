#!/usr/bin/env python3
"""
Check downloaded PDFs for corruption and remove invalid files
"""

from pathlib import Path

def is_pdf(filepath):
    """Check if file is actually a PDF"""
    try:
        with open(filepath, 'rb') as f:
            header = f.read(4)
            return header == b'%PDF'
    except:
        return False

def main():
    pdf_dir = Path("cvpr_2024_papers")
    
    if not pdf_dir.exists():
        print("No cvpr_2024_papers directory found")
        return
    
    pdf_files = list(pdf_dir.glob("*.pdf"))
    print(f"Checking {len(pdf_files)} PDF files...")
    
    valid_count = 0
    invalid_files = []
    
    for pdf_file in pdf_files:
        if is_pdf(pdf_file) and pdf_file.stat().st_size > 1024:
            valid_count += 1
            print(f"✓ {pdf_file.name}")
        else:
            invalid_files.append(pdf_file)
            print(f"✗ {pdf_file.name} - INVALID")
    
    print(f"\nSummary:")
    print(f"  Valid PDFs: {valid_count}")
    print(f"  Invalid files: {len(invalid_files)}")
    
    if invalid_files:
        print(f"\nInvalid files found:")
        for f in invalid_files:
            size = f.stat().st_size
            print(f"  {f.name} ({size} bytes)")
        
        response = input(f"\nDelete {len(invalid_files)} invalid files? (y/N): ")
        if response.lower() == 'y':
            for f in invalid_files:
                f.unlink()
                print(f"Deleted: {f.name}")
            print("Invalid files removed. Run the download script again to retry these.")

if __name__ == "__main__":
    main()