from lxml import etree

def make_xml(toc):
    toc_el = etree.Element('toc')
    doc = etree.ElementTree(toc_el)
    for toc_entry in toc:
        entry_el = etree.SubElement(toc_el, 'entry')
        etree.SubElement(entry_el, 'tocpage').text = str(toc_entry['tocpage'])
        etree.SubElement(entry_el, 'pagenum').text = toc_entry['pagenum']
        title_el = etree.SubElement(entry_el, 'title')
        for title_word in toc_entry['title']:
            word_el = etree.SubElement(title_el, 'word')
            etree.SubElement(word_el, 'text').text = title_word.text
            etree.SubElement(word_el, 'box').text = title_word.box.tostring()
    return toc_el
        
