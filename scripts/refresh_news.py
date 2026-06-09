#!/usr/bin/env python3
"""Hermes Agent News Dashboard v2 — Live scraping + auto-classification + multi-source.
Designed to run every hour on the big dog (edgexpert-3315).
Output: hermes-news.html + index.html, pushed to GitHub Pages."""

import subprocess, re, time, json, sys, os, urllib.parse, html as html_mod, hashlib
from datetime import datetime, timedelta

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_DIR = os.path.dirname(SCRIPT_DIR)
OUTPUT = os.path.join(REPO_DIR, 'hermes-news.html')
CACHE_FILE = os.path.join(REPO_DIR, 'articles_cache.json')
TEMP_DIR = os.path.join(REPO_DIR, '.cache')
os.makedirs(TEMP_DIR, exist_ok=True)

# ── Search keywords (expand coverage) ──
KEYWORDS_TOUTIAO = [
    'Hermes Agent',
    'Hermes Agent 教程',
    '开源 Agent',
    'Agent 框架',
    'AI Agent 开源',
]

# ── Hardcoded known articles (seeded from previous version, won't be dropped) ──
KNOWN_AIDS = {
    # Nous官方
    '7640179600638640691', '7638572546434187816', '7645667832075747840',
    '7645986285256983086', '7648188951836819983', '7647601050165314054',
    '7643350458471432719', '7648449847879598632', '7647079952025748010',
    '7647087326006362634',
    # 桌面端
    '7635221067510661678', '7647116327815004681', '7647506717697147411',
    # 使用技巧
    '7644478681368298030', '7646548779113447945', '7647453021424632347',
    '7647382424342561326', '7647803749016060468', '7646320837049451054',
    '7648573296262283830', '7643436240741663282', '7647327124176650771',
    '7637824243127943720', '7648341842836177471', '7648322570018439714',
    '7642882285217301026', '7648904459526930990', '7641610534575555098',
    '7636787204831855147', '7641841406922719779', '7645593586309874185',
    '7639716328214987264', '7644756189770809890', '7648238839336600099',
    '7640886355874054707', '7637795065187844658', '7644061889143521834',
    '7641500884056277547', '7646377943224091162', '7639573759058084361',
    '7641887176417935910',
    # 技术前沿
    '7648136448679428648', '7645565147485946394', '7639537395188220468',
    '7641958581205598735', '7646971342521008675', '7643996441664324123',
    '7641211790886322734', '7647326909512041003', '7647451200408814114',
    '7624751638158262820', '7648167953774412288',
    # 对比评测
    '7637134413758857737', '7641203762963186202', '7647098263330390563',
    '7643467636051640859', '7642544476619276815',
    # 行业动态
    '7647527883178656265', '7647354528748143156', '7647426230203023926',
    '7638883032220320299', '7641967788726288946', '7639732898819555849',
    '7642432058253492755', '7632156040942944818', '7648696819765019151',
    '7645267185520558619', '7645136402216239659', '7639525656560222758',
    '7641964704432194074', '7637053787407909411', '7641162958797685288',
}

# ChatGPT-written articles to EXCLUDE (low quality / irrelevant)
EXCLUDE_TITLE_PATTERNS = [
    r'^ChatGPT.*写.*', r'^用ChatGPT', r'^让ChatGPT', r'^我和ChatGPT',
    r'爱马仕.*(?:包包|丝巾|皮带|手袋|配货|香水|成衣|珠宝|口红|皮鞋|围巾)',
    r'(?:包包|丝巾|皮带|手袋|配货|香水|成衣|珠宝|口红)\s*爱马仕',
    r'Hermès', r'Birkin', r'Kelly',
    r'养龙虾',  # unrelated
    r'^.*(?:招聘|求职|征婚|兼职).*$',  # no job ads
]

MAX_ARTICLES = 200  # max articles to display on page
METADATA_CACHE_TTL = 86400  # re-fetch metadata after 24h


# ═══════════════════════════════════════════
# SOURCE SCRAPERS
# ═══════════════════════════════════════════

def curl_get(url, timeout=15, headers=None):
    """Robust curl wrapper."""
    cmd = ['curl', '-s', '-L', '-m', str(timeout), url]
    if headers:
        for k, v in headers.items():
            cmd.extend(['-H', f'{k}: {v}'])
    else:
        cmd.extend(['-H', 'User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'])
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout + 5)
        return r.stdout
    except:
        return ''


def extract_toutiao_articles(html):
    """Extract articles from so.toutiao.com search HTML. Returns list of dicts."""
    articles = {}
    blocks = re.split(r'<div class="result-content"', html)
    for bi, block in enumerate(blocks):
        if bi == 0: continue
        if '"self_article"' not in block: continue
        if '"cell_type":20' in block: continue  # skip ads

        gid_m = re.search(r'group_id":\s*"(\d{19})"', block)
        if not gid_m: continue
        aid = gid_m.group(1)

        link_m = re.search(r'href="[^"]*"[^>]*class="text-ellipsis text-underline-hover"[^>]*>', block)
        if not link_m: continue
        title_end = block.find('</a>', link_m.end())
        if title_end < 0: continue
        title_raw = block[link_m.end():title_end]
        title = html_mod.unescape(re.sub(r'<[^>]+>', '', title_raw)).strip()
        title = re.sub(r'\s+', ' ', title).strip()

        # Skip non-Hermes content
        if not any(kw in title for kw in ['Hermes', 'hermes', 'Hermès', 'Agent', 'agent',
                                           '爱马仕', 'AI Agent', 'ai agent']):
            continue
        # Skip exclusions
        skip = False
        for pat in EXCLUDE_TITLE_PATTERNS:
            if re.search(pat, title):
                skip = True
                break
        if skip: continue
        if len(title) < 6: continue

        # Extract source & time
        source_spans = re.findall(r'<span class="text-ellipsis[^"]*"[^>]*>\s*([^<]{2,30})\s*<', block)
        source = ''
        time_str = ''
        for sp in source_spans:
            sp = sp.strip()
            if re.match(r'\d+[天小时分秒]前|刚刚', sp) or re.match(r'\d{1,2}月\d{1,2}日', sp):
                time_str = sp
            elif not source and not sp.isdigit() and len(sp) >= 2:
                source = sp

        # Description
        desc_m = re.search(r'class="text-default text-m[^"]*"[^>]*>\s*(?:<span[^>]*>)?([^<]{50,500})', block)
        desc = html_mod.unescape(desc_m.group(1)) if desc_m else ''

        key = title[:40]
        if key not in articles:
            articles[key] = {
                'title': title[:150],
                'url': f'https://www.toutiao.com/article/{aid}/',
                'aid': aid,
                'source': source,
                'desc': desc[:300],
                'time': time_str,
                'pub': '',
                'reads': '',
                'likes': 0,
                'comments_count': 0,
            }
    return list(articles.values())


def scrape_toutiao():
    """Scrape so.toutiao.com with multiple keywords and modes."""
    all_articles = {}
    seen_aids = set()

    for keyword in KEYWORDS_TOUTIAO:
        encoded = urllib.parse.quote(keyword)
        for pd_param in ['synthesis', 'information']:
            for page in range(8):  # 8 pages per mode
                url = f'https://so.toutiao.com/search?dvpf=pc&keyword={encoded}&pd={pd_param}&page_num={page}'
                html = curl_get(url, timeout=12)
                if not html:
                    continue
                extracted = extract_toutiao_articles(html)
                for a in extracted:
                    if a['aid'] not in seen_aids:
                        seen_aids.add(a['aid'])
                        all_articles[a['title'][:40]] = a
                if len(extracted) == 0:
                    break  # no more results
                time.sleep(0.3)

    return list(all_articles.values())


def scrape_wechat():
    """Scrape Sogou WeChat search for public account articles."""
    encoded = urllib.parse.quote('Hermes Agent')
    articles = {}
    seen_titles = set()

    for page in range(3):
        page_url = f'https://weixin.sogou.com/weixin?type=2&query={encoded}&ie=utf8'
        if page > 0:
            page_url += f'&page={page}'
        html = curl_get(page_url, timeout=12)
        if not html:
            continue

        blocks = re.split(r'<div class="txt-box[^"]*"', html)
        for block in blocks[1:]:
            title_m = re.search(r'<a[^>]*target="_blank"[^>]*>(.*?)</a>', block)
            if not title_m: continue
            title = html_mod.unescape(re.sub(r'<[^>]+>', '', title_m.group(1))).strip()
            title = re.sub(r'\s+', ' ', title)
            title = re.sub(r'<!--red_beg-->|<!--red_end-->', '', title)
            if not title or len(title) < 8: continue

            lower = title.lower()
            keep_keywords = ['agent', 'ai', '智能', '开源', '部署', '安装', '教程', '评测',
                             '版本', '更新', '桌面', '模型', '代码', '编程', '技术', '工具',
                             '开发', '架构', '学习', 'vs', '对比', '实测', '指南', '入门']
            skip_keywords = ['爱马仕', '包包', '奢侈品', '丝巾', '皮带', '手袋', '配货',
                             'hermès', 'birkin', 'kelly', '口红', '香水', '成衣', '珠宝',
                             '招聘', '求职']
            if any(k in lower for k in skip_keywords): continue
            if not any(k in lower for k in keep_keywords): continue

            title_key = title[:40]
            if title_key in seen_titles: continue
            seen_titles.add(title_key)

            link_m = re.search(r'href="(/link\?url=[^"]+)"', block)
            link = 'https://weixin.sogou.com' + link_m.group(1) if link_m else ''

            src_m = re.search(r'class="all-time-y2"[^>]*>([^<]+)', block)
            source = html_mod.unescape(src_m.group(1)).strip() if src_m else '微信公众号'

            desc_m = re.search(r'class="txt-info[^"]*"[^>]*>([^<]+)', block)
            desc = html_mod.unescape(re.sub(r'<[^>]+>', '', desc_m.group(1))).strip() if desc_m else ''

            fake_aid = f'wx_{hashlib.md5(link.encode()).hexdigest()[:12]}'
            articles[title_key] = {
                'title': title[:150], 'url': link, 'source': source,
                'desc': desc[:300], 'aid': fake_aid, 'time': '', 'pub': '',
                'reads': '0', 'likes': 0, 'comments_count': 0,
            }
        time.sleep(0.3)

    return list(articles.values())


def scrape_hn():
    """Scrape Hacker News via Algolia API."""
    articles = {}
    for keyword in ['Hermes Agent', 'AI Agent']:
        encoded = urllib.parse.quote(keyword)
        url = f'https://hn.algolia.com/api/v1/search?query={encoded}&tags=story&hitsPerPage=10'
        try:
            data = json.loads(curl_get(url, timeout=8))
            for hit in data.get('hits', []):
                title = hit.get('title', '')
                if not title or len(title) < 8: continue
                key = title[:40]
                if key in articles: continue
                points = hit.get('points', 0)
                comments = hit.get('num_comments', 0)
                url_link = hit.get('url', '') or hit.get('story_url', '') or \
                           f'https://news.ycombinator.com/item?id={hit.get("objectID", "")}'
                articles[key] = {
                    'title': title[:150], 'url': url_link, 'source': 'Hacker News',
                    'aid': f'hn_{hashlib.md5(url_link.encode()).hexdigest()[:12]}',
                    'time': '', 'pub': '', 'reads': str(points),
                    'likes': points, 'comments_count': comments,
                }
        except:
            pass
    return list(articles.values())


def scrape_github_issues():
    """Fetch hot GitHub issues from hermes-agent repo."""
    url = 'https://api.github.com/repos/NousResearch/hermes-agent/issues?state=open&sort=comments&direction=desc&per_page=10'
    articles = {}
    try:
        issues = json.loads(curl_get(url, timeout=8, headers={'User-Agent': 'HermesNewsBot', 'Accept': 'application/vnd.github.v3+json'}))
        if isinstance(issues, list):
            for issue in issues:
                title = issue.get('title', '')
                if not title: continue
                num = issue.get('number', 0)
                comments = issue.get('comments', 0)
                url_link = issue.get('html_url', '')
                key = title[:40]
                if key not in articles:
                    articles[key] = {
                        'title': f'#{num} {title[:130]}', 'url': url_link,
                        'source': 'GitHub Issues',
                        'aid': f'gh_{num}', 'time': '', 'pub': '',
                        'reads': str(comments), 'likes': 0, 'comments_count': comments,
                    }
    except:
        pass
    return list(articles.values())


def scrape_reddit():
    """Scrape Reddit via public JSON API."""
    articles = {}
    subreddits = ['LocalLLaMA', 'ArtificialIntelligence', 'opensource', 'MachineLearning']
    for sub in subreddits:
        url = f'https://www.reddit.com/r/{sub}/search.json?q=Hermes+Agent&restrict_sr=on&sort=new&limit=10'
        try:
            html = curl_get(url, timeout=10, headers={'User-Agent': 'HermesNewsBot/1.0'})
            data = json.loads(html)
            for child in data.get('data', {}).get('children', []):
                d = child.get('data', {})
                title = d.get('title', '')
                if not title: continue
                if not any(kw in title for kw in ['Hermes', 'hermes', 'Agent', 'agent']):
                    continue
                key = title[:40]
                if key in articles: continue
                permalink = d.get('permalink', '')
                url_link = f'https://www.reddit.com{permalink}' if permalink else ''
                score = d.get('score', 0)
                comments = d.get('num_comments', 0)
                sub_name = d.get('subreddit', 'reddit')
                articles[key] = {
                    'title': title[:150], 'url': url_link,
                    'source': f'r/{sub_name}', 'aid': f'rd_{hashlib.md5(url_link.encode()).hexdigest()[:12]}',
                    'time': '', 'pub': '', 'reads': str(score),
                    'likes': score, 'comments_count': comments,
                }
        except:
            pass
        time.sleep(0.5)
    return list(articles.values())


def scrape_zhihu():
    """Scrape Zhihu search results."""
    encoded = urllib.parse.quote('Hermes Agent')
    articles = {}
    seen = set()

    url = f'https://www.zhihu.com/search?type=content&q={encoded}'
    html = curl_get(url, timeout=12, headers={
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        'Cookie': 'z_c0=;',  # no auth needed for search
    })
    if not html:
        return []

    # Try to extract from JSON embedded data
    blocks = re.split(r'<div class="ContentItem', html)
    for block in blocks[1:]:
        title_m = re.search(r'data-za-detail-view-path-module="ContentItem"[^>]*>\s*<meta[^>]*itemprop="url"[^>]*content="[^"]*question/(\d+)"', block)
        # Try multiple patterns to find title
        title = ''
        # Try h2 with link
        t_m = re.search(r'<h2[^>]*>\s*<a[^>]*>(.*?)</a>', block)
        if t_m:
            title = html_mod.unescape(re.sub(r'<[^>]+>', '', t_m.group(1))).strip()
        if not title:
            t_m = re.search(r'data-search-actuality="title"[^>]*>([^<]+)', block)
            if t_m:
                title = html_mod.unescape(t_m.group(1)).strip()
        if not title or len(title) < 8: continue
        title = re.sub(r'\s+', ' ', title)

        if not any(kw in title for kw in ['Hermes', 'hermes', 'Agent', 'agent', '爱马仕']):
            continue

        key = title[:40]
        if key in seen: continue
        seen.add(key)

        # Extract URL
        url_m = re.search(r'href="(https?://[^"]+zhihu[^"]*question/\d+[^"]*)"', block)
        link = url_m.group(1) if url_m else f'https://www.zhihu.com/search?q={encoded}'

        # Source - extract author
        author_m = re.search(r'data-author-name="([^"]+)"', block)
        source = html_mod.unescape(author_m.group(1)).strip() if author_m else '知乎'

        articles[key] = {
            'title': title[:150], 'url': link, 'source': f'知乎·{source}',
            'aid': f'zh_{hashlib.md5(link.encode()).hexdigest()[:12]}',
            'time': '', 'pub': '', 'desc': '',
            'reads': '', 'likes': 0, 'comments_count': 0,
        }

    return list(articles.values())


# ═══════════════════════════════════════════
# AUTO-CLASSIFICATION
# ═══════════════════════════════════════════

def classify_article(title, source=''):
    """Auto-classify an article into a category. Rule-based."""
    t = title.lower()
    s = source.lower()

    # Nous官方
    if any(k in t for k in ['v0.', '版本更新', '更新了', '炸裂更新', '新功能',
                             'novus', 'nous', '官方', '发布']):
        if any(k in t for k in ['安装', '教程', '指南', '配置', '入门']):
            pass  # fall through to check other rules
        else:
            return 'Nous官方'

    # 桌面端
    if any(k in t for k in ['桌面', '可视化', '控制台', 'tui', 'gui', '界面']):
        return '桌面端'

    # 使用技巧
    if any(k in t for k in ['安装', '部署', '教程', '指南', '配置', '入门', '上手',
                             '小白', '保姆', '零基础', '极速', '2分钟', '3分钟',
                             '攻略', '步骤', '设置', '技巧', '方法', '必看',
                             '避坑', '实战', '接入', '接进', '转接',
                             '从入门到', '完全指南', '全流程', '本地部署',
                             '记忆增强', 'free cpu', '学习指南', '全解析',
                             '升级', '基础']):
        return '使用技巧'

    # 技术前沿
    if any(k in t for k in ['架构', '源码', '原理', '底层', '机制', '策略',
                             '解析', '拆解', '设计', '技术', '工程', '优化',
                             'token', 'token', '工具', 'skill', 'mcp',
                             '评测', '实测', '三个月', '蹲了', '研究',
                             '工具搜索', 'tool search', '省token',
                             '危险命令', '安全', '刹车', '隔离', '通信',
                             '子agent', '控制台', 'webhook',
                             '外部事件', '定时', '自动化', '渐进式',
                             '单日', 'token', '登顶']):
        return '技术前沿'

    # 对比评测
    if any(k in t for k in ['对比', 'vs', '评测', '谁更强', '区别',
                             'benchmark', 'bench', '性能']):
        return '对比评测'

    # Default: 行业动态
    return '行业动态'


# ═══════════════════════════════════════════
# METADATA FETCH
# ═══════════════════════════════════════════

def fetch_metadata(articles):
    """Fetch read count, likes, comments, publish time for Toutiao articles."""
    results = []
    total = len(articles)
    for i, a in enumerate(articles):
        aid = a.get('aid', '')
        if not aid or not aid.isdigit() or len(aid) != 19:
            # Not a Toutiao article, skip metadata fetch
            results.append(a)
            continue
        url = f'https://m.toutiao.com/article/{aid}/'
        html = curl_get(url, timeout=8, headers={
            'User-Agent': 'Mozilla/5.0 (Linux; Android 13) AppleWebKit/537.36',
            'Accept-Language': 'zh-CN,zh;q=0.9',
        })
        if html:
            m = re.search(r'RENDER_DATA"[^>]*>([^<]+)', html)
            if m:
                try:
                    decoded = urllib.parse.unquote(m.group(1))
                    data = json.loads(decoded)
                    info = data.get('articleInfo', {})
                    if isinstance(info, str): info = json.loads(info)
                    ts = info.get('publishTime', '')
                    if ts:
                        dt = datetime.fromtimestamp(int(ts))
                        a['pub'] = dt.strftime('%Y-%m-%d')
                    a['reads'] = info.get('impressionCount', a.get('reads', ''))
                    a['likes'] = info.get('diggCount', a.get('likes', 0))
                    a['comments_count'] = info.get('commentCount', a.get('comments_count', 0))
                except:
                    pass
        results.append(a)
        if i < total - 1:
            time.sleep(0.25)
        sys.stderr.write(f'\r  Metadata: [{i+1}/{total}]')
    return results


# ═══════════════════════════════════════════
# GITHUB STATS
# ═══════════════════════════════════════════

def fetch_github():
    """Fetch GitHub repo stats."""
    try:
        repo = json.loads(curl_get('https://api.github.com/repos/NousResearch/hermes-agent', timeout=8))
        release = json.loads(curl_get('https://api.github.com/repos/NousResearch/hermes-agent/releases/latest', timeout=8))
        return {
            'stars': repo.get('stargazers_count', 186534),
            'forks': repo.get('forks_count', 32090),
            'release_tag': release.get('tag_name', ''),
            'release_url': release.get('html_url', ''),
        }
    except:
        return {'stars': 186534, 'forks': 32090, 'release_tag': '', 'release_url': ''}


# ═══════════════════════════════════════════
# CACHE HELPERS
# ═══════════════════════════════════════════

def load_cache():
    """Load cached articles."""
    if os.path.exists(CACHE_FILE):
        try:
            with open(CACHE_FILE) as f:
                return json.load(f)
        except:
            return []
    return []


def save_cache(articles):
    """Save articles to cache."""
    with open(CACHE_FILE, 'w', encoding='utf-8') as f:
        json.dump(articles, f, ensure_ascii=False, default=str)


# ═══════════════════════════════════════════
# HTML GENERATION
# ═══════════════════════════════════════════

def fmt_reads(n):
    """Format number for display."""
    if n >= 10000:
        return f'{n/10000:.1f}万'
    if n >= 1000:
        return f'{n/1000:.1f}千'
    return str(n)


def gen_score(title, reads, likes, comments):
    """Generate a score (1-5) for an article."""
    score = 3
    if reads >= 5000 or likes >= 500 or comments >= 50:
        score = 5
    elif reads >= 2000 or likes >= 200 or comments >= 20:
        score = 4
    elif reads >= 500 or likes >= 50 or comments >= 5:
        score = 3
    elif reads >= 100:
        score = 2
    else:
        score = 2

    if any(k in title for k in ['评测', '实测', '拆解', '详解', '架构', '对比', '指南', '教程', '避坑']):
        score = min(5, score + 1)
    if len(title) < 12:
        score = max(1, score - 1)
    return score


def gen_keymsg(title, cat):
    """Generate a key message summary."""
    t = title
    # Use the same rich mapping from v1 for known patterns
    mapping = {
        '安装': '安装与配置相关教程',
        '教程': '实用教程与操作指南',
        '指南': '详细指南与最佳实践',
        '入门': '快速入门指引',
        '配置': '配置方法与技巧',
        '部署': '部署与安装流程',
        '桌面': '桌面端功能体验',
        'v0.16': 'v0.16新版本特性详解',
        'v0.15': 'v0.15升级实测体验',
        '对比': '多维度对比分析',
        '评测': '深度使用评测报告',
        '架构': '技术架构深度解析',
        '源码': '源码级技术分析',
        '更新': '最新版本更新内容',
        '技巧': '实用技巧分享',
        '避坑': '常见问题与避坑指南',
        '记忆': '持久记忆机制解析',
        '安全': '安全机制与审批链路',
        'webhook': '外部事件触发机制',
        '定时': '定时自动化任务',
        'token': 'Token优化策略',
        '微信': '接入微信的完整流程',
        '英伟达': '英伟达定制版Hermes Agent',
        'nvidia': 'NVIDIA优化版Hermes Agent',
    }
    for pat, msg in mapping.items():
        if pat in t:
            return msg
    return f'{cat}相关报道'


def gen_html(articles, fresh_count, cached_count, github):
    """Generate the full HTML page."""
    # Sort by pub date (newest first), unknown dates at the end
    def sort_key(a):
        pub = a.get('pub', '')
        if pub and re.match(r'\d{4}-\d{2}-\d{2}', pub):
            return pub
        return '0000-00-00'
    articles.sort(key=sort_key, reverse=True)

    # Limit total displayed
    articles = articles[:MAX_ARTICLES]

    # Build category counts
    cat_count = {}
    for a in articles:
        cat = a.get('cat', '行业动态')
        cat_count[cat] = cat_count.get(cat, 0) + 1

    # Category buttons
    total = len(articles)
    cat_buttons = f'<button class="fb a" data-c="all" onclick="fc(\'all\')">📋 全部 <span class="n">{total}</span></button>'
    for ck in ['Nous官方', '桌面端', '使用技巧', '技术前沿', '对比评测', '行业动态',
               '微信公众号', 'Hacker News', 'GitHub Issues']:
        cnt = cat_count.get(ck, 0)
        if cnt > 0:
            cat_buttons += f'<button class="fb" data-c="{ck}" onclick="fc(\'{ck}\')">{ck} <span class="n">{cnt}</span></button>'

    # Cards
    cards_html = ''
    for a in articles:
        pub = a.get('pub', '') or '2026-06'
        reads = int(a.get('reads', '0')) if str(a.get('reads', '0')).isdigit() else 0
        likes = a.get('likes', 0) or 0
        comments = a.get('comments_count', 0) or 0
        title = a.get('title', 'Untitled')
        url = a.get('url', '#')
        source = a.get('source', '未知来源')
        cat = a.get('cat', '行业动态')
        keymsg = gen_keymsg(title, cat)
        score = gen_score(title, reads, likes, comments)
        stars_full = '★' * score + '☆' * (5 - score)
        reads_fmt = fmt_reads(reads)

        cards_html += f'''    <div class="card" data-date="{pub}" data-read="{reads}" data-like="{likes}" data-reply="{comments}" data-score="{score}" data-cat="{cat}">
      <div class="card-inner">
        <div class="card-main">
          <div class="tag tag-{cat}">{cat}</div>
          <a href="{url}" target="_blank" class="title">{title}</a>
          <div class="meta">
            <span>✍️ {source}</span><span>🕐 {pub}</span>
            <span class="s">👁 {reads_fmt}</span>
            <span class="s">💬 {comments}</span>
            <span class="s">👍 {likes}</span>
          </div>
        </div>
        <div class="card-keymsg">{keymsg}</div>
        <div class="card-score">{stars_full}<br><span class="score-num">{score}.0</span></div>
      </div>
    </div>
'''

    # Stats
    total_reads = sum(int(a.get('reads', '0')) if str(a.get('reads', '0')).isdigit() else 0 for a in articles)
    total_likes = sum(a.get('likes', 0) or 0 for a in articles)
    stars = f"{github['stars']:,}" if github.get('stars') else '186,534'
    forks = f"{github['forks']:,}" if github.get('forks') else '32,090'

    now_str = datetime.now().strftime('%Y-%m-%d %H:%M')
    refresh_info = f'<div class="refresh-info">🕐 最后更新: {now_str} | 📥 本次爬取 {fresh_count} 篇 | 📚 页面展示 {total} 篇 | 💾 缓存 {cached_count} 篇</div>'

    html = f'''<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>马哥新闻@caesaryin</title>
<style>
*{{margin:0;padding:0;box-sizing:border-box}}
body{{font-family:-apple-system,"PingFang SC","Microsoft YaHei",sans-serif;background:#f0f2f5;color:#1a1a2e;max-width:960px;margin:0 auto;padding:16px}}
.hdr{{background:linear-gradient(135deg,#1a1a2e,#16213e,#0f3460);color:#fff;padding:28px 24px;border-radius:16px;margin-bottom:16px}}
.hdr h1{{font-size:24px}}.hdr h1 span{{color:#e94560}}
.hdr .sub{{font-size:13px;opacity:.6;margin-top:6px}}
.hdr .s{{display:flex;gap:20px;margin-top:12px;font-size:12px;opacity:.7}}
.hdr .s strong{{color:#e94560}}
.tb{{background:#fff;border-radius:12px;padding:14px 18px;margin-bottom:14px;box-shadow:0 1px 4px rgba(0,0,0,.06);display:flex;flex-wrap:wrap;align-items:center;gap:10px}}
.tb .l{{font-size:13px;color:#666;font-weight:500}}
.sg{{display:flex;gap:6px;flex-wrap:wrap}}
.sb{{padding:5px 12px;border:1px solid #e0e0e0;border-radius:6px;background:#fff;cursor:pointer;font-size:13px;color:#555}}
.sb:hover{{border-color:#e94560;color:#e94560}}
.sb.a{{background:#e94560;color:#fff;border-color:#e94560}}
.ob{{padding:5px 10px;border:1px solid #e0e0e0;border-radius:6px;background:#fff;cursor:pointer;font-size:13px;color:#555}}
.ob:hover{{border-color:#7c3aed;color:#7c3aed}}
.ob.a{{background:#7c3aed;color:#fff;border-color:#7c3aed}}
.fg{{display:flex;gap:6px;flex-wrap:wrap}}
.fb{{padding:5px 12px;border:1px solid #e0e0e0;border-radius:16px;background:#fff;cursor:pointer;font-size:12px;color:#555}}
.fb:hover{{border-color:#e94560;color:#e94560}}
.fb.a{{background:#1a1a2e;color:#fff;border-color:#1a1a2e}}
.fb .n{{display:inline-block;background:#f0f0f0;color:#888;font-size:11px;padding:0 5px;border-radius:8px;margin-left:3px}}
.fb.a .n{{background:rgba(255,255,255,.2);color:rgba(255,255,255,.7)}}
.nc{{font-size:13px;color:#999;padding:4px 0 8px}}
.card{{background:#fff;border-radius:12px;padding:16px 18px;margin-bottom:10px;box-shadow:0 1px 4px rgba(0,0,0,.06);border-left:3px solid transparent}}
.card:hover{{box-shadow:0 4px 16px rgba(0,0,0,.1);transform:translateX(2px)}}
.tag{{display:inline-block;font-size:11px;padding:2px 8px;border-radius:4px;margin-bottom:6px;font-weight:500}}
.tag-Nous官方{{background:#fce4ec;color:#c62828}}
.tag-桌面端{{background:#e3f2fd;color:#1565c0}}
.tag-使用技巧{{background:#e8f5e9;color:#2e7d32}}
.tag-技术前沿{{background:#f3e5f7;color:#6a1b9a}}
.tag-对比评测{{background:#fbe9e7;color:#bf360c}}
.tag-行业动态{{background:#fff3e0;color:#e65100}}
.tag-微信公众号{{background:#07c160;color:#fff}}
.tag-Hacker News{{background:#ff6600;color:#fff}}
.tag-GitHub Issues{{background:#24292f;color:#fff}}
.card .title{{display:block;font-size:15px;font-weight:600;line-height:1.5;color:#1a1a2e;text-decoration:none}}
.card .title:hover{{color:#e94560;text-decoration:underline}}
.card .meta{{font-size:12px;color:#999;margin-top:10px;display:flex;flex-wrap:wrap;align-items:center;gap:12px}}
.card-inner{{display:flex;gap:16px;align-items:stretch}}
.card-main{{flex:1;min-width:0}}
.card-keymsg{{flex:0 0 200px;font-size:12px;color:#666;background:#f8f9fa;border-left:2px solid #e94560;padding:8px 12px;border-radius:0 6px 6px 0;display:flex;align-items:center;line-height:1.6}}
.card-score{{flex:0 0 60px;text-align:center;display:flex;flex-direction:column;align-items:center;justify-content:center;color:#f59e0b;font-size:16px;line-height:1.4}}
.score-num{{font-size:11px;color:#999;margin-top:2px}}
.gh{{background:#fff;border-radius:12px;padding:12px 18px;margin-bottom:14px;box-shadow:0 1px 4px rgba(0,0,0,.06);display:flex;flex-wrap:wrap;align-items:center;gap:12px;font-size:13px}}
.gh .g{{color:#555}}.gh .g strong{{color:#e94560}}
.gh a{{color:#7c3aed;text-decoration:none;font-size:12px}}
.refresh-info{{background:#f0f4ff;border:1px solid #d0d7ff;border-radius:8px;padding:8px 14px;margin-bottom:12px;font-size:12px;color:#555}}
.ft{{text-align:center;font-size:12px;color:#bbb;padding:24px 0;border-top:1px solid #eee;margin-top:16px}}
.ft a{{color:#e94560;text-decoration:none}}
@media(max-width:600px){{body{{padding:10px}}.hdr{{padding:20px 16px}}}}
</style>
</head>
<body>

<div class="hdr">
<h1>&#128269; 马哥新闻 <span>@caesaryin</span></h1>
<div class="sub">2026年06月 · 多源聚合 · 共 {total} 篇</div>
<div class="s"><div>&#128240; <strong>{total}</strong> 篇</div><div>&#128065; <strong>{fmt_reads(total_reads)}</strong> 总阅读</div><div>&#128077; <strong>{fmt_reads(total_likes)}</strong> 总点赞</div></div>
</div>

<div class="gh">
<span class="g">&#11088; GitHub <strong>{stars}</strong> Stars</span>
<span class="g">&#127829; <strong>{forks}</strong> Forks</span>
<a href="https://github.com/NousResearch/hermes-agent" target="_blank">&#128640; GitHub &rarr;</a>
</div>

{refresh_info}

<div class="tb">
<span class="l">&#128204; 排序：</span>
<div class="sg">
<button class="sb a" data-k="date" onclick="s('date')">&#128338; 时间</button>
<button class="sb" data-k="read" onclick="s('read')">&#128065; 阅读</button>
<button class="sb" data-k="like" onclick="s('like')">&#128077; 点赞</button>
<button class="sb" data-k="reply" onclick="s('reply')">&#128172; 评论</button>
<button class="sb" data-k="score" onclick="s('score')">⭐ 评分</button>
</div>
<button class="ob a" id="ob" onclick="to()">&#9660; 降序</button>
<span class="l" style="margin-left:8px">&#127991; 分类：</span>
<div class="fg">{cat_buttons}</div>
</div>

<div class="nc" id="nc">显示 {total} 篇报道</div>
<div id="c">{cards_html}</div>

<div class="ft">
<p>数据来源：<a href="https://so.toutiao.com/search?keyword=Hermes%20Agent" target="_blank">今日头条</a> · <a href="https://weixin.sogou.com/weixin?type=2&query=Hermes+Agent" target="_blank">微信公众号</a> · <a href="https://news.ycombinator.com/" target="_blank">Hacker News</a> · <a href="https://www.reddit.com/search/?q=Hermes+Agent" target="_blank">Reddit</a> · <a href="https://github.com/NousResearch/hermes-agent/issues" target="_blank">GitHub Issues</a></p>
<p>由小马S（Hermes Agent）自动聚合 · 每小时更新 <span id="ftd"></span></p>
</div>

<script src="/hermes-agent-news/scripts/news-sort.js"></script>
<script>
function s(k){{window._newsSort(k)}}
function to(){{window._newsToggle()}}
function fc(c){{window._newsFilter(c)}}
</script>
</body>
</html>'''
    with open(OUTPUT, 'w', encoding='utf-8') as f:
        f.write(html)
    # Also write index.html for GitHub Pages
    import shutil
    shutil.copy2(OUTPUT, os.path.join(REPO_DIR, 'index.html'))
    return len(html)


# ═══════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════

if __name__ == '__main__':
    print('=== Hermes Agent News Refresh v2 ===')
    start_time = time.time()

    # 1. Load cache
    cached = load_cache()
    # Build lookup by aid
    cached_by_aid = {}
    for a in cached:
        aid = a.get('aid', '')
        if aid:
            cached_by_aid[aid] = a
    print(f'Loaded {len(cached)} cached articles')

    # 2. Scrape all sources
    print('Scraping Toutiao...')
    toutiao = scrape_toutiao()
    print(f'  {len(toutiao)} fresh articles')

    print('Scraping WeChat...')
    wechat = scrape_wechat()
    print(f'  {len(wechat)} wechat articles')

    print('Scraping Hacker News...')
    hn = scrape_hn()
    print(f'  {len(hn)} HN articles')

    print('Scraping GitHub Issues...')
    gh = scrape_github_issues()
    print(f'  {len(gh)} GitHub issues')

    print('Scraping Reddit...')
    reddit = scrape_reddit()
    print(f'  {len(reddit)} Reddit articles')

    print('Scraping Zhihu...')
    zhihu = scrape_zhihu()
    print(f'  {len(zhihu)} Zhihu articles')

    # 3. Merge: fresh articles + cached + known articles
    merged = {}
    fresh_aids = set()

    # a) Fresh Toutiao articles first (they're current)
    for a in toutiao:
        aid = a['aid']
        a['cat'] = classify_article(a['title'], a['source'])
        merged[aid] = a
        fresh_aids.add(aid)

    # b) Fresh WeChat articles
    for a in wechat:
        aid = a['aid']
        if aid not in merged:
            a['cat'] = '微信公众号'
            merged[aid] = a
            fresh_aids.add(aid)

    # c) Fresh HN articles
    for a in hn:
        aid = a['aid']
        if aid not in merged:
            a['cat'] = 'Hacker News'
            merged[aid] = a
            fresh_aids.add(aid)

    # d) Fresh GitHub Issues
    for a in gh:
        aid = a['aid']
        if aid not in merged:
            a['cat'] = 'GitHub Issues'
            merged[aid] = a
            fresh_aids.add(aid)

    # e) Fresh Reddit/Zhihu articles (may be empty if blocked)
    for src in [reddit, zhihu]:
        for a in src:
            aid = a['aid']
            if aid not in merged:
                a['cat'] = classify_article(a['title'], a.get('source', ''))
                merged[aid] = a
                fresh_aids.add(aid)

    # f) Cached articles that aren't in fresh but are known or have metadata
    for a in cached:
        aid = a.get('aid', '')
        if aid and aid not in merged:
            # Only keep cached articles that have valid metadata or are known
            if aid in KNOWN_AIDS or a.get('pub') or a.get('reads'):
                if 'cat' not in a:
                    a['cat'] = classify_article(a.get('title', ''), a.get('source', ''))
                merged[aid] = a

    articles = list(merged.values())
    print(f'Total after merge: {len(articles)} articles ({len(fresh_aids)} fresh)')

    # 4. Fetch metadata for Toutiao articles that need it
    need_meta = []
    for a in articles:
        aid = a.get('aid', '')
        if aid and aid.isdigit() and len(aid) == 19:
            if not a.get('pub') or not a.get('reads') or a['reads'] == '0':
                if aid in fresh_aids:  # only fetch for fresh articles
                    need_meta.append(a)
    if need_meta:
        print(f'Fetching metadata for {len(need_meta)} fresh articles...')
        fetched = fetch_metadata(need_meta)
        for fa in fetched:
            faid = fa.get('aid', '')
            if faid:
                for i, a in enumerate(articles):
                    if a.get('aid') == faid:
                        articles[i] = fa
                        break
    else:
        print('All articles have metadata, skipping fetch')

    # 5. Get GitHub stats
    print('Fetching GitHub data...')
    github = fetch_github()
    print(f'  Stars: {github["stars"]}, Forks: {github["forks"]}')

    # 6. Generate HTML
    print('Generating HTML...')
    size = gen_html(articles, len(toutiao), len(cached), github)
    print(f'  Written {size} bytes to {OUTPUT}')

    # 7. Save cache
    save_cache(articles)
    print(f'  Saved {len(articles)} articles to cache')

    elapsed = time.time() - start_time
    print(f'Done! ({elapsed:.1f}s)')
