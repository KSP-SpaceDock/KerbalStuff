import urllib.parse
from urllib.parse import parse_qs, urlparse
from typing import Dict, Any

from markdown import Markdown
from markdown.extensions import Extension
from markdown.inlinepatterns import Pattern
from markdown.util import etree

EMBED_RE = r'\[\[(?P<url>.+?)\]\]'


def embed_youtube(link: urllib.parse.ParseResult) -> etree.Element:
    q = parse_qs(link.query)
    v = q['v'][0]
    el = etree.Element('iframe')
    el.set('width', '100%')
    el.set('height', '600')
    el.set('frameborder', '0')
    el.set('allowfullscreen', '')
    el.set('src', '//www.youtube-nocookie.com/embed/' + v + '?rel=0')
    return el


def embed_imgur(link: urllib.parse.ParseResult) -> etree.Element:
    a = link.path.split('/')[2]
    el = etree.Element('iframe')
    el.set('width', '100%')
    el.set('height', '550')
    el.set('frameborder', '0')
    el.set('allowfullscreen', '')
    el.set('src', '//imgur.com/a/' + a + '/embed')
    return el


class EmbedPattern(Pattern):
    def __init__(self, pattern: str, m: Markdown, configs: Dict[str, Any]) -> None:
        super(EmbedPattern, self).__init__(pattern, m)
        self.config = configs

    def handleMatch(self, m: Markdown) -> etree.Element:
        d = m.groupdict()
        url = d.get('url')
        if not url:
            el = etree.Element('span')
            el.text = "[[" + url + "]]"
            return el
        try:
            link = urlparse(url)
            host = link.hostname
        except:
            el = etree.Element('span')
            el.text = "[[" + url + "]]"
            return el
        el = None
        try:
            if host == 'youtube.com' or host == 'www.youtube.com':
                el = embed_youtube(link)
            if host == 'imgur.com' or host == 'www.imgur.com':
                el = embed_imgur(link)
        except:
            pass
        if el is None:
            el = etree.Element('span')
            el.text = "[[" + url + "]]"
            return el
        return el


class KerbDown(Extension):
    def __init__(self, **kwargs: int) -> None:
        super().__init__(**kwargs)
        self.config: Dict[str, Any] = {}

    # noinspection PyMethodOverriding
    def extendMarkdown(self, md: Markdown, md_globals: Any) -> None:
        # BUG: the base method signature is INVALID, it's a bug in flask-markdown
        md.inlinePatterns['embeds'] = EmbedPattern(EMBED_RE, md, self.config)
        md.registerExtension(self)
