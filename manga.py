# Usage: python3 manga.py [-i] <website.com>
# <website.com>: specifically, a webpage from "comick.app". Can be an index
#   (manga listing) or a single chapter.
# -i: (optional) if present, we interpret <website.com> as an index, and
#   repeatedly attempt to download websites until we have cached everything.
#   This is useful because there appears to be a timeout limit with scraping
#   websites; after about 40 chapter downloads, the scraper process is killed.
#   This essentially launches a sub-process to handle downloads, and repeatedly
#   maintains sub-processes until they no longer download anything.

import sys
import os
import re
import time
import requests
import tempfile
import subprocess
from itertools import groupby
from PIL import Image
import pandas as pd
from selenium import webdriver
from selenium.webdriver import Chrome
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from webdriver_manager.chrome import ChromeDriverManager


# Scrapes the html from the webpage at the URL. Assumes the URL contains data
# that's dynamically loaded, so we wait 5 seconds before scraping content.
# Returns the HTML as a string.
def scrape(url, delay=2):
    options = webdriver.ChromeOptions()
    options.headless = False
    options.page_load_strategy = 'none'
    driver = Chrome(options=options)

    driver.get(url)
    time.sleep(delay)
    text = driver.page_source

    driver.quit()
    return text


# Returns 1 if writing a new file was ssuccessful, 0 if a cached file already
# existed (thus, no new one was created).
def create_pdf(website, delay=2, outdir=os.getcwd(), outname=None):
    # Does the website name have a number surrounded by hyphens in it? If
    # so, take it as the chapter index; otherwise, use the website name
    # as the file name.
    m = re.search('\-([\d]+)\-', website)
    chapter = m.group(1).zfill(4) \
        if m is not None \
        else website[website.rindex('/')+1:]
    if outname is None:
        outname = outdir[outdir.rfind('/')+1:] + '-' + chapter
    pdf = outdir + '/' + outname + '.pdf'

    if os.path.exists(pdf):
        print(f'Website "{website}" already cached ... skipped')
        return 0

    print(f'Scraping "{website}" ... ', flush=True, end='')
    try:
        html = scrape(website, delay)
    except:
        print('error')
        return create_pdf(website, delay + 5, outdir, outname)
    print('done')

    regex = r'<div [a-zA-Z0-9="\s-]+?><img alt=\".+?\" ' \
            r'src=\"(.+?)\" style=.+?<\/div>'
    urls = [match.group(1) for match in re.finditer(regex, html)]

    # Save each image to a file
    with tempfile.TemporaryDirectory() as tempdir:
        images = []
        for url in urls:
            name = tempdir + '/' + url[url.rindex('/')+1:]
            print(f'Saving "{name}" ... ', flush=True, end='')
            try:
                content = requests.get(url).content
                with open(name, 'wb') as f:
                    f.write(content)
                images.append(Image.open(name).convert('RGB'))
            except:
                print('error')
                time.sleep(10)
                return create_pdf(website, delay + 5, outdir, outname)
            print('done')

        # Caused if we didn't completely load the page. Retry.
        if len(images) == 0:
            print('Error: no images found.')
            time.sleep(10)
            return create_pdf(website, delay + 5, outdir, outname)

        if not os.path.exists(outdir):
            os.makedirs(outdir)

        print(f'Saving to "{pdf}" ... ', flush=True, end='')
        images[0].save(pdf, save_all=True, append_images=images[1:])
        print('done')

        return 1


# Returns how many new files were created.
def chapter_index(url, delay=2):
    print(f'Scraping "{url}" ... ', flush=True, end='')
    html = scrape(url, delay)
    print('done')

    # Get the part with specifically the table in it. Should be the third
    # table in the html that contains the chapters.
    html = re.findall('<table.+?>.+?</table>', html)[2]

    exp = r'<a class="py-3 .+?" href="(.+?)">.+?' \
          r'<span class="font-semibold" title=".+?">Ch. (\d+\.?\d*)</span>' \
          r'<span class=".+?">(.+?)</span>.+?' \
          r'<div class="text-sm !no-link">(\d+)</div>.+?</a>'
    reg = re.compile(exp)

    # Format: (chapter, index, number, name, downloads)
    items = []
    while True:
        match = re.search(reg, html)
        if match is None: break
        html = html[match.start()+1:]

        chapter   = match.group(1)
        index     = match.group(2).replace('.', '-')
        name      = match.group(3).strip()
        downloads = match.group(4)

        if 'https:' not in chapter:
            chapter = 'https://comick.app' + chapter

        num = re.search('-(\d+\.?\d*)-', chapter)
        print('Chapter:', chapter)
        if num is not None:
            potential_num = num.group(1).replace('.', '-')
            if potential_num != index: continue

        group = (chapter, index, name, downloads)
        items.append(group)

    if len(items) == 0:
        print('Error: no chapters found.')
        time.sleep(10)
        return chapter_index(url, delay + 5)

    # Group the items together with the same chapter.
    grouped = [list(v) for i, v in groupby(items, lambda x: x[1])]

    # Pick the item from each group that has the highest download count.
    total = 0
    for group in grouped:
        group.sort(key=lambda x: int(x[3]), reverse=True)
        top = group[0]
        print('Top:', top)
        man = re.search(r'https://comick.app/comic/(.+?)/.+', top[0]).group(1)
        chap = ''.join(
            ch.lower() if ch.isalpha() or ch.isdigit() or ch == '-' else ''
            for ch in top[2].replace(' ', '-')
        )
        nums = top[1].split('-')
        num = nums[0].zfill(4) + ('' if len(nums) == 1 else ('-' + nums[1]))
        total += create_pdf(top[0], delay, man, man + '_' + num + '_' + chap)

    return total


if __name__ == '__main__':
    arg = sys.argv[-1]
    total = 0
    if sys.argv[1] == '-i':
        while True:
            last_line = ''
            command = ['python3', 'manga.py', sys.argv[-1]]
            print('Launching subprocess.')
            with (subprocess.Popen(command, stdout=subprocess.PIPE, bufsize=1, \
                    universal_newlines=True)) as p:
                for line in p.stdout:
                    print(line, end='')
                    last_line = line

            if 'Total' not in last_line:
                print('Error: process may have terminated unexpectedly.')
                sys.exit(1)
            else:
                last_count = last_line.split(' ')[-1].strip()
                if last_count == '0':
                    sys.exit(0) # We're done! No more files to process.
                else:
                    print(f'Continuing process, items created: {last_count}')

    elif os.path.exists(arg):
        # Assume this is a file containing websites, each separated by a line.
        # Each website contains a manga chapter, so scrape the chapter and
        # output it to a pdf, where the pdf goes to a new directory.
        with open(arg, 'r') as f:
            outdir = arg[:arg.rindex('/')]
            if not os.path.exists(outdir):
                os.makedirs(outdir)

            for line in f.readlines():
                total += create_pdf(line.strip(), outdir)

    else:
        # What kind of webpage is this? If it's an index, it takes the form
        # "https://comick.app/comic/<name>". If it's a chapter, it's instead
        # "https://comick.app/comic/<name>/<chapter>".
        slashes = sum(1 if ch == '/' else 0 for ch in arg)
        if slashes == 4:
            # This is an index. Scrape all the links from this.
            total += chapter_index(arg)
        elif slashes == 5:
            # This is a chapter. Output the chapter to a pdf.
            total += create_pdf(arg)
        else:
            print('Error: improperly formatted link. Must be a link to ' \
                  'a manga chapter or an index containing several chapters.')
            sys.exit(1)

    print('Total:', total)
