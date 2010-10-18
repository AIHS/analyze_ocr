import sys
from difflib import SequenceMatcher, get_close_matches, Match
from extract_sorted import extract_sorted
from rnums import rnum_to_int
from interval import Interval, IntervalSet

from collections import namedtuple


from windowed_iterator import windowed_iterator

def l(s):
    sys.stderr.write(str(s) + '\n')

class pagenocand(namedtuple('pagenocand', 'numtype page_index val word_index')):
    pass


def check_toc(toc):
    # reject if:
    # - any title is too long.
    # - page numbers aren't monotonic
    # - some entries have pageno w/o title/label
    # - if toc pages skip
    # - if a toc item contains numbers?
    if len(toc) < 4:
        return False
    prevno = 0
    prevtocpage = toc[0]['tocpage']
    for ti in toc:
        if len(ti['title']) > 60:
            return False
        if len(ti['title'].strip()) == 0 and len(ti['label'].strip()) == 0:
            return False
        if int(ti['pagenum']) < prevno:
            return False
        prevno = int(ti['pagenum'])
        if ti['tocpage'] > prevtocpage + 1:
            return False
        prevtocpage = ti['tocpage']
    return True






def make_toc(iabook, pages):
    contentscount = iabook.get_contents_count()

    # contentscount = 0

    skipfirst = 0
    n = 5 # XXX should be higher?
    max_assumed_toc = 2
    # max_assumed_toc = 1
    n_optimistic = max_assumed_toc
    tcs = []
    thresh = 5 # if some tc page goes above this score, then...
    starttoc = 0 # starttoc is set to skip prev pages.
    max_assumed_toc_len = 5
    endtoc = sys.maxint
    for page in pages:
        if (len(page.info['number']) == 0
            and 'pageno_guess' in page.info):
            page.info['number'] = str(page.info['pageno_guess'])

        # if 'pageno_guess' in page.info:
        #     print 'yah'
        #     page.info['number'] = str(page.info['pageno_guess'])

        # skip on if we're waiting for a contents page
        if (len(tcs) == 0
            and contentscount > 0
            and page.info['type'] != 'contents'):
            continue
        if page.index < skipfirst:
            continue
        # l("%s: %s %s" % (page.index, page.info['number'],
        #                      page.info['type']))
        wipetil = 0
        score = 0
        for i, tc in enumerate(tcs):
            if i < starttoc:
                continue
            if i > endtoc:
                continue
            tc.match_page(page)
            if tc.score > thresh:
                starttoc = i
                if endtoc != sys.maxint:
                    endtoc = starttoc + max_assumed_toc_len

        # if contentscount is
        # 0: build contents pages for first n pages - need to remember to score all
        # 2+: bnuild contents pages exactly for designated pages
        # 1: skip pages before 1rst contents page, build n_optimistic pages, remember to score later pages
        if ((contentscount == 0 and len(tcs) < n)
            or (contentscount == 1 and len(tcs) < n_optimistic)
            or (contentscount > 1 and len(tcs) < contentscount
                and page.info['type'] == 'contents')):
                tcs.append(TocCandidate(page))
                # if True:
                #     break
    # for tc in tcs:
    #     tc.printme()
    qdresult = []
    all_pageno_cands = []
    result = []
    for i, tc in enumerate(tcs):
        if tc.score > thresh:
            for match in tc.matches:
                info = tc.matchinfo[match]
                tocitem_words = info.matchwords()
                pagenum = info.nearno
                if info.nearno != -1:
                    pagenum = tc.words[pagenum]
                labelwords, titlewords = guess_label(tocitem_words)
                result.append({'level':1, 'label':(' '.join(labelwords)).strip(),
                               'title':(' '.join(titlewords)).strip(), 'pagenum':pagenum,
                               'tocpage':i
                               })
            if i == 0:
                all_pageno_cands += tc.pageno_cands
            else:
                all_pageno_cands += tc.pageno_cands_unfiltered
                # all_pageno_cands += tc.pageno_cands

            # qdresult += tc.get_qdtoc()
    if len(all_pageno_cands) > 0:
        all_pageno_cands_f = extract_sorted(all_pageno_cands)
        # print all_pageno_cands
    for i, tc in enumerate(tcs):
        if tc.score > thresh:
            qdresult += tc.get_qdtoc(all_pageno_cands_f)

    return result, qdresult


labels = ('chapter', 'part', 'section', 'book',
#              'preface', 'appendix', 'footnotes'
          )
numbers = ('one', 'two', 'three', 'four', 'five',
           'six', 'seven', 'eight', 'nine', 'ten',
           'eleven', 'twelve', 'thirteen', 'fourteen', 'fifteen',
           'sixteen', 'seventeen', 'eighteen', 'nineteen', 'twenty',
           )
def guess_label(words):
    labelwords = []
    if len(words) > 1:
        if words[0].lower() in labels:
            labelwords.append(words.pop(0))
            if len(words) > 1 and (words[0].isdigit()
                                   or rnum_to_int(words[0]) != 0
                                   or words[0] in numbers):
                labelwords.append(words.pop(0))
    # XXX could put guess at '4 oysters 45' here (get 4)
    return labelwords, words


class RangeMatch(object):
    # intervals, in the intervalset, point here
    def __init__(self, tc, page, match):
        self.page = page
        self.tc = tc # Give all pages words... and make toccandidate a page, to get round this?
        self.score = match.size
        self.pageindex = page.index
        self.pageno = page.info['number']
        self.nearno = -1 # index of nearby page_cand
        self.match = match
        self.notes = ''
    def __repr__(self):
        nearno_mapped = 0
        if self.nearno != -1:
            nearno_mapped = self.tc.words[self.nearno]
        words = ' '.join(self.tc.words[i] for i in range(self.match.b, self.match.b + self.match.size)).encode('utf-8')
        return "%s\tscore %s pageno %s nearno i%s v%s\t%s notes %s" % (self.match,
                                                                  self.score,
                                                                  self.pageno,
                                                                  self.nearno,
                                                                  nearno_mapped,
                                                                  words,
                                                                  self.notes)
    def matchwords(self):
        adj = 0
        if self.nearno != -1:
            adj = self.nearno - (self.match.b + self.match.size)
        return self.tc.words[self.match.b:self.match.b + self.match.size + adj]


class RangeSet(object):
    def __init__(self):
        self.s = []
    def add(r):
        self.s.append(r)
    def overlaps(r):
        for rs in s:
            if ((rs.match.b < r.match.b
                 and rs.match.b + rs.match.size >= r.match.b)
                or (rs.match.b >= r.match.b
                    and r.match.b + r.match.size >= rs.match.b)):
                yield rs

class TocCandidate(object):
    def __init__(self, page):
        self.page = page
        self.matcher = SequenceMatcher()
        self.words = [word for word in page.get_words()]
        for i in range(4):
            if i >= len(self.words):
                break
            # if i < len(self.words):
            #     self.words.pop(i)
            if self.words[i] == 'contents':
                self.words[i] = ''
            if self.words[i] == 'page':
                self.words[i] = ''
        self.wordhash = {}
        for word in self.words:
            self.wordhash[word] = True
        self.matcher.set_seq2(self.words)
        # l('\n'.join('%s:%s' % (i, w) for i, w in enumerate(self.words)))
        # l('content len: %s' % len(self.words))
        self.lookaside = {}
        self.pageno_cands = self.find_pageno_cands(page, filtered=True)
        self.pageno_cands_unfiltered = self.find_pageno_cands(page, filtered=False)
        self.matches = IntervalSet()
        self.matchinfo = {}
        self.score = 0

    def printme(self):
        # print ' '.join('%s:%s' % (i, w) for i, w in enumerate(self.words))
        # print 'content len: %s' % len(self.words)
        # print "%s %s" % (len(self.matches), self.matches)
        # for ival in self.matches:
        #     info = self.matchinfo[ival]
        #     print "%s %s" % (ival, info)
        pass

    def find_nearnos(self, match):
        # XXX worry later about contained.  for now: just next and prev:
        # note that current next, prev is from *end* of match
        left = None
        right = None

        # def cands():
        #     for c in self.pageno_cands:
        #         yield c

        # windowed_nearnos = windowed_iterator(cands(), 4)
        # for right in windowed_nearnos:
        #     if match.b + match.size - 1 < right.word_index:
        #         break;
        #     left = right
        #     return windowed_nearnos.neighbors()

        for right in self.pageno_cands:
            if match.b + match.size - 1 < right.word_index:
                break;
            left = right
        return left, right


    def add_match(self, page, match):
        # l('ADDING ' + str(match))
        info = RangeMatch(self, page, match)
        # l(info)
        pageno = page.info['number']
        pagenoval = rnum_to_int(pageno)
        if pagenoval == 0 and len(pageno) > 0:
            pagenoval = int(pageno)

        matchint = Interval.between(match.b, match.b + match.size)

        overlaps = [m for m in self.matches
                    if m & matchint]

        # if nearnos matches either, mark flag and amp score
        if pageno:
            nearnos = self.find_nearnos(match)
            # l("GREPME near is [%s] pagenoval %s" % (nearnos, pagenoval))
            # for no in nearnos[1], nearnos[0]:
            if nearnos is None: # XXX SHOULDN"T BE NEEDED!!!!!!!!!!!!
                nearnos = []
            for no in nearnos[1], nearnos[0]:
            # for no in nearnos:
                if no is not None:
                    # l(no.val)
                    if no.val == pagenoval:
                        info.notes += 'nearno: %s' % pageno
                        # l("GOODMATCH tc %s, %s %s" % (self.page.index, pageno, self.score))
                        self.score += 1
                        info.nearno = no.word_index
                        break
                    if no.val > pagenoval - 10 and match.a < 10:
                        self.score += .01
                        break

        # cases: no overlap
        if len(overlaps) == 0:
            self.matchinfo[matchint] = info
            self.matches = self.matches + IntervalSet([matchint])
        else:
            start = match.b
            end = match.b + match.size
            for i in overlaps:
                oinfo = self.matchinfo[i]
                ostart = oinfo.match.b
                oend = oinfo.match.b + oinfo.match.size
                scootback = 0
                if ostart < start:
                    scootback = start - ostart
                    start = ostart
                if oend > end:
                    end = oend
                info.match = Match(info.match.a - scootback, start, end - start)
                if oinfo.nearno != -1:
                    # assert(info.nearno == -1)
                    info.nearno = oinfo.nearno
                # info.score += oinfo.score
                # info.pageno = oinfo.pageno
                # info.notes = info.notes + ' ' + info.notes
                # for opageno in oinfo.pagenos:
                #     opagecount = oinfo.pagenos[opageno]
                #     if opageno in info.pagenos:
                #         info.pagenos[opageno] += opagecount
                #     else:
                #         info.pagenos[opageno] = opagecount
            self.matches += IntervalSet([matchint])
            (new_i,) = [m for m in self.matches if m & matchint]
            self.matchinfo[new_i] = info

        # else:
        #     for m, info in overlaps:
        #         if info.pageno == page.info


        # print "%s %s" % (len(self.matches), self.matches)
        # for ival in self.matches:
        #     info = self.matchinfo[ival]
        #     print "%s %s" % (ival, info)

        # overlap

        # for existing_match in self.matches:

        # --> get array of matching stuff in matches.
        # existing_matches = IntervalSet([matchint]) &

    def find_pageno_cands(self, page, filtered=True):
        """ Find the set of all numbers on this page that don't
        e.g. follow 'chapter', then find the largest increasing subset
        of these numbers; we consider it likely that these'll be book
        page numbers """
        # XXX i18m someday
        labels = ('chapter', 'part', 'section', 'book')
        def get_page_cands(page):
            lastword = ''
            for i, word in enumerate(page.get_words()):
                if lastword in labels:
                    lastword = word
                    continue
                r = rnum_to_int(word)
                # print word.encode('utf-8')
                # if r != 0:
                #     yield pagenocand('0roman', page.index, r, i)
                if word.isdigit():
                    val = int(word)
                    if val < 999:
                        # XXX replace above check with book page count
                        # if avail.
                        yield pagenocand('1arabic', page.index, int(word), i)
                lastword = word
        def printword(c):
            ar, val, loc = c
            print "%s %s - %s" % (ar, val, self.words[loc])
        page_cands = [c for c in get_page_cands(page)]

        result = page_cands
        # print page_cands

        if filtered and len(page_cands) > 0:
            extracted_orig = extract_sorted(page_cands)
            result = extracted_orig

        # less_greedy_heuristic = False
        less_greedy_heuristic = True
        # try to guess at the situation where we've grabbed a compact
        # sequence of number that aren't pagenos - common case is
        # chapter numbers.  If first numbers are closely spaced, and
        # skipping them still gives a reasonable (different) sequence,
        # go ahead and skip them.
        if filtered and less_greedy_heuristic:
            if len(page_cands) != 0:
                # import pdb; pdb.set_trace()
                slop = 1
                if (len(extracted_orig) > 3
                    and extracted_orig[0].val + 2 >= extracted_orig[1].val
                    and extracted_orig[1].val + 2 >= extracted_orig[2].val):
                    page_cands_filtered = []
                    for c in page_cands:
                        if c != extracted_orig[1] and c != extracted_orig[2]:
                            page_cands_filtered.append(c)
                    extracted_filtered = extract_sorted(page_cands_filtered)
                    # did we just lose a pair we wanted?
                    # see if extracted_filtered is the same, but for the missing two
                    unchanged_sort = False
                    if (len(extracted_filtered) + 2 == len(extracted_orig)
                        and extracted_filtered[0] == extracted_orig[0]):
                        i = 1
                        while i < len(extracted_orig) - 2:
                            if extracted_filtered[i] != extracted_orig[i + 2]:
                                break
                            i += 1
                        unchanged_sort = True
                    if (unchanged_sort
                        or len(extracted_orig) + 4 < len(extracted_filtered)):
                        # too much loss, go with orig
                        result = extracted_orig
                    else:
                        result = extracted_filtered
                        # print extracted_filtered
                    # result = extracted_filtered
                    # print extracted_filtered
        return result

    def match_page(self, page):
        # for line in page.get_lines():
        #     print '%s %s %s' % ('FIRSTLINE', page.index, ' '.join(w.text for w in line.get_words()))
        #     break
        words = [word for word in page.get_words()][:30]
        # print ' '.join(words).encode('utf-8')
        for i, word in enumerate(words):
            words[i] = self.reify(word)
        # print words
        self.matcher.set_seq1(words)
        page_matches = self.matcher.get_matching_blocks()
        page_matches.pop() # lose trailing non-match
        def smallmatch(m):
            smallwords = ('a', 'and', 'the', 'i', 'in', 'to', 'of', 'with')
            smallphrases = (('in', 'the'))
            if m.size > 2:
                return False
            if m.size == 1:
                word = self.words[m.b]
                if word in smallwords:
                    return True
            if m.size == 2:
                word = self.words[m.b]
                word2 = self.words[m.b + 1]
                if (word, word2) in smallphrases:
                    return True
            if len(word) < 3:
                return True
            return False
        page_matches = [m for m in page_matches if not smallmatch(m)]
        for page_match in page_matches:
            # print "%s %s" % (page_match,
            #                  self.decode_match(page_match).encode('utf-8'))
            self.add_match(page, page_match)
    def decode_match(self, match):
        return ' '.join(self.words[i] for i in range(match.b, match.b + match.size))
    def reify(self, word):
        if word in self.wordhash:
            return word
        if word in self.lookaside:
            return self.lookaside[word]
        cands = get_close_matches(word, self.words, n=1, cutoff=.9)
        if len(cands) > 0:
            candidate = cands[0]
            # print "%s --> %s" % (word.encode('utf-8'), candidate.encode('utf-8'))
            self.lookaside[word] = candidate
            return candidate
        self.lookaside[word] = word
        return word

    def get_qdtoc(self, all_pageno_cands):
        # pobj = abbyypage(page)
        valid_pages = {}
        for c in all_pageno_cands:
            if c.page_index == self.page.index:
                valid_pages[c.word_index] = c
        # for c in self.pageno_cands:
        #     valid_pages[c.word_index] = c
        # print valid_pages
        words_so_far = []
        firstword = True
        prev_word = ''
        result = []
        for i, word in enumerate(self.words):
            if firstword:
                if word.lower() == 'contents':
                    prev_word = word
                    continue
                firstword = False
            if i in valid_pages:
                labelwords, titlewords = guess_label(words_so_far)
                result.append({'level':1, 'label':(' '.join(labelwords)).strip(),
                               'title':(' '.join(titlewords)).strip(), 'pagenum':word,
                               'tocpage':self.page.index
                               })
                words_so_far = []
            else:
                words_so_far.append(word)
            prev_word = word
        return result
