import logging
from urllib.parse import urlparse

import mwparserfromhell
import requests

from graphbrain.cognition.agent import Agent


IGNORE_SECTIONS = {'See also',
                   'Explanatory notes',
                   'References',
                   'Other sources',
                   'Further reading',
                   'External links',
                   'Sources',
                   'Selected bibliography'}


def url2title_and_lang(url):
    p = urlparse(url)

    netloc = p.netloc.split('.')
    if len(netloc) < 3 or 'wikipedia' not in netloc:
        raise RuntimeError('{} is not a valid wikipedia url.'.format(url))
    lang = netloc[0]

    path = [part for part in p.path.split('/') if part != '']
    if len(path) != 2 or path[0] != 'wiki':
        raise RuntimeError('{} is not a valid wikipedia url.'.format(url))
    title = path[1]

    return title, lang


def read_wikipedia(title, lang='en'):
    params = {
        'action': 'query',
        'format': 'json',
        'titles': title,
        'prop': 'extracts|revisions',
        'explaintext': '',
        'rvprop': 'ids',
    }

    api_url = 'http://{}.wikipedia.org/w/api.php'.format(lang)
    r = requests.get(api_url, params=params)
    request = r.json()

    for page_id in request['query']['pages']:
        return request['query']['pages'][page_id]['extract']

    return None


def clean_sections(sections):
    csecs = []
    for section in sections:
        if type(section) == str:
            if len(section) > 0:
                csecs.append(section)
        elif type(section) == dict:
            cdict = {}
            for title in section:
                if title not in IGNORE_SECTIONS:
                    cdict[title] = clean_sections(section[title])
            if len(cdict) > 0:
                csecs.append(cdict)
    return csecs


def sections2texts(sections):
    paragraphs = []
    for section in sections:
        if type(section) == str:
            paragraphs.append(section)
        if type(section) == dict:
            for title in section:
                paragraphs += sections2texts(section[title])
    return paragraphs


class Wikipedia(Agent):
    def __init__(self, name, progress_bar=True, logging_level=logging.INFO):
        super().__init__(
            name, progress_bar=progress_bar, logging_level=logging_level)

    def run(self):
        url = self.system.get_url(self)
        parser = self.system.get_parser(self)
        outfile = self.system.get_outfile(self)

        title, lang = url2title_and_lang(url)
        text = read_wikipedia(title, lang)

        wikicode = mwparserfromhell.parse(text)

        sections = []
        section_stack = [sections]
        level = 1
        for node in wikicode.nodes:
            if type(node) == mwparserfromhell.nodes.heading.Heading:
                title = node.title.strip()
                if node.level <= level:
                    section_stack.pop()
                if node.level < level:
                    section_stack.pop()
                new_section = []
                section_stack[-1].append({title: new_section})
                section_stack.append(new_section)
                level = node.level
            elif type(node) == mwparserfromhell.nodes.text.Text:
                text = str(node).strip().replace('\n', ' ')
                section_stack[-1].append(text)

        sections = clean_sections(sections)
        texts = sections2texts(sections)

        for text in texts:
            for op in self.system.parse_results2ops(parser.parse(text)):
                yield op

        if outfile:
            with open(outfile, 'wt') as f:
                for text in texts:
                    f.write('{}\n'.format(text))
