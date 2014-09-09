#from calais import Calais

def format_atom(item, config):
    #calais = Calais(config.calais_keys.key)
    link = item['short_link']
    title_short = item['title'][:80]
    title_ext = item['title'][80:]

    #r = calais.analyze_url(i['link'])

    tags = ""
    for tag in item['tags']:
        if len(link) + len(title_short) + len(tag) + len(tags) + 2 < (140):
            if len(tags) == 0: tags = tag
            else: tags = " ".join([tags, tag])

    while len(link) + len(title_short) + len(tag) + len(tags) + 2 < (140) and len(title_ext) > 0:
        title_short += title_ext[:1]
        title_ext = title_ext[1:]

    if len(title_ext) > 0:
        title_short = "".join([title_short[:-3].strip(), "..."])

    return "{0}\n{1}\n{2}".format(title_short, link, tags)

