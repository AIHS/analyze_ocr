from lxml import etree

def make_xml(toc):
    top_el = etree.Element('ocr_analysis')
    doc = etree.ElementTree(top_el)
    toc_el = etree.SubElement(top_el, 'toc')
    for toc_entry in toc:
        entry_el = etree.SubElement(toc_el, 'entry')
        etree.SubElement(entry_el, 'level').text = str(toc_entry['level'])

        refpage_el = etree.SubElement(entry_el, 'refpage')
        page_el = etree.SubElement(refpage_el, 'page')
        etree.SubElement(page_el, 'name').text = toc_entry['pagenum']
        if toc_entry.get('pageleaf'):
            etree.SubElement(page_el, 'leaf').text = toc_entry['pageleaf']
        if toc_entry.get('pageindex'):
            etree.SubElement(page_el, 'index').text = str(toc_entry['pageindex'])
        title_el = etree.SubElement(entry_el, 'title')
        for title_word in toc_entry['title']:
            word_el = etree.SubElement(title_el, 'word')
            etree.SubElement(word_el, 'text').text = title_word.text
            etree.SubElement(word_el, 'box').text = title_word.box.tostring()

        tocpage_el = etree.SubElement(entry_el, 'tocpage')
        page_el = etree.SubElement(tocpage_el, 'page')
        if toc_entry.get('tocleaf'):
            etree.SubElement(page_el, 'leaf').text = toc_entry['tocleaf']
        if toc_entry.get('tocindex'):
            etree.SubElement(page_el, 'index').text = str(toc_entry['tocindex'])
    return top_el
        
