"""Turn text into search terms. Articles and queries go through the same steps."""
import re
import unicodedata

# A word is letters and digits, optionally joined by apostrophes: don't, o'clock.
WORD = re.compile(r"[^\W_]+(?:'[^\W_]+)*")
QUOTED = re.compile(r'"([^"]*)"')
MAX_TERM_LENGTH = 100


def fold(text):
    """Lowercase and drop accents, so Café, CAFE and cafe are the same word."""
    text = text.replace('’', "'").replace('“', '"').replace('”', '"')
    text = unicodedata.normalize('NFKD', text.casefold())
    return ''.join(char for char in text if not unicodedata.combining(char))


def stem(word):
    """Undo English plurals with Harman's S-stemmer: harbours -> harbour.

    It only touches plurals, so it rarely joins words with different
    meanings. Both sides use it, so an odd result such as "news" -> "new"
    still matches consistently.
    """
    if word.endswith("'s"):
        word = word[:-2]
    if len(word) <= 3:
        return word
    if word.endswith('ies') and not word.endswith(('eies', 'aies')):
        return word[:-3] + 'y'
    if word.endswith('es') and not word.endswith(('aes', 'ees', 'oes')):
        return word[:-1]
    if word.endswith('s') and not word.endswith(('us', 'ss')):
        return word[:-1]
    return word


def analyze(text):
    """Return the terms in text, in order. Positions are list indexes."""
    return [stem(word)[:MAX_TERM_LENGTH] for word in WORD.findall(fold(text))]


def parse_query(query):
    """Split a query into its terms and its "quoted phrases".

    Every term must appear in a result. A phrase must also appear with its
    words next to each other, in the same field.
    """
    query = fold(query)
    phrases = [terms for terms in map(analyze, QUOTED.findall(query)) if len(terms) > 1]
    terms = list(dict.fromkeys(analyze(query.replace('"', ' '))))
    return terms, phrases
