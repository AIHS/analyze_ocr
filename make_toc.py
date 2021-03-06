
import sys
from difflib import SequenceMatcher, get_close_matches, Match
from extract_sorted import extract_sorted
from rnums import rnum_to_int
from interval import Interval, IntervalSet

# possible to not need this? shove all into iabook?
import re
from collections import namedtuple
from windowed_iterator import windowed_iterator

VERBOSE = True

# just look at 1rst n words in page when deciding whether to mark it
# as a TOC.
FIRSTN = 30

# try to guess at the situation where we've grabbed a compact
# sequence of number that aren't pagenos - common case is
# chapter numbers.  If first numbers are closely spaced, and
# skipping them still gives a reasonable (different) sequence,
# go ahead and skip them.
# less_greedy_heuristic = True
less_greedy_heuristic = False

# how far across the page a number need be before it's considered a
# pageno candidate.
PAGENO_X_RATIO = .3

SKIP_IF_LAST_TOC_FILLED = True



class pagenocand(namedtuple('pagenocand', 'numtype val word_index page_index')):
    pass

def l(result, comment):
    result['comments'] += comment + '\n'

def failit(tr, s):
    l(tr, s)
    tr['isok'] = False
    tr['isok'] = True


def simple_make_toc(iabook, pages):
    result = { 'isok': True,
               'has_contents': True,
               'has_pagenos': True,
               'qdtoc': [],
               'qdtoc_tuples': [],
               }
    contentscount = iabook.get_contents_count()
    if contentscount == 0:
        result['has_contents'] = False
        return result
    if not iabook.has_pagenos():
        result['has_pagenos'] = False
    tcs = []
    for page in pages:
        if page.info['type'] == 'contents':
            tcs.append(TocCandidate(page))
            tcs[-1].score = 50
            if len(tcs) == contentscount:
                break

    # (for qdtoc algorithm)
    # Go through all tc candidates
    # - append to toc struct based on matches / nearno
    # - collect from tc: pageno cands = pageno_cands / pageno_cands_unfiltered
    all_pageno_cands = []
    for i, tc in enumerate(tcs):
        if i == 0:
            all_pageno_cands += tc.pageno_cands
        else:
            all_pageno_cands += tc.pageno_cands_unfiltered

    # pull sorted increasing set from pageno_cands - hopefully this'll
    # filter out chaff pagenos, as ToCs always have increasing page
    # numbers.
    if len(all_pageno_cands) > 0:
        all_pageno_cands_f = extract_sorted(all_pageno_cands)

        for i, tc in enumerate(tcs):
            toc_els, tuple_toc_els = tc.get_qdtoc(all_pageno_cands_f, iabook)
            result['qdtoc'] += toc_els
            result['qdtoc_tuples'] += tuple_toc_els
        result['qdtoc'] = cleanup_toc(result['qdtoc'])
    return result


def make_toc(iabook, pages, contents_leafs=None, not_contents_leafs=None):
    result = { 'isok': True,
               'has_contents': True,
               'has_pagenos': True,
               'comments':'http://archive.org/stream/%s\n' % (iabook.book_id),
               'toc':[],
               'qdtoc':[]
               }
    result['comments'] += 'http://openlibrary.org/ia/%s\n' % (iabook.book_id)
    contentscount = iabook.get_contents_count()
    if contentscount == 0:
        result['has_contents'] = False
    if not iabook.has_pagenos():
        result['has_pagenos'] = False

    # XXXmm these might help with speed

#     if iabook.has_pagenos():
#         result['failedbkno'] = 'nope'
#         failit(result, 'already saw these books')
#         return result


#     if not iabook.has_pagenos():
#         result['failedbkno'] = 'nope'
#         failit(result, 'failed bc no pagenos marked')
#         return result

#     if contentscount == 0:
#         result['failedbkno'] = 'nope'
#         failit(result, 'failed bc no contents page marked')
#         return result


    # loop through all pages.  For some set of early pages, make
    # TocCandidate objs - and compare each subsequent page to each
    # TocCandidate created so far, subject to some rules intended to
    # speed things up.  Accumulate TocCandidate scores / info

    # XXX detect title page and only accept contents, if after?

    tcs = []
    toc_threshold = 3 # if some tc page goes above this score, then...

    # skip early book pages altogether
    skip_pages_until_index = 0

    # Try this many toc pages (starting at skip_pages) if none marked
    toc_count_to_try_if_no_contents_info = 40 # 20

    # Try this many toc pages if 1 is marked
    toc_count_to_try_if_contents_info = 40 # 8

    # fail if more than this many contiguous good toc pages are seen
    # should be less than two vars above...
    max_allowed_toc_len = 40 # 7

    # these values control comparing book pages to a sliding window of
    # already-found toc pages.  Can result in early toc candidates
    # being 'shadowed' by spurious later ones - e.g. lists of
    # illustration.
    windowed_match = False

    # first candidate toc page to compare subsequent pages to; this is
    # adjusted upward as new candidate pages are found.
    toc_window_start = 0

    # at most this many toc pages are checked against current body
    # page forward of the most recently threshold-making toc
    toc_window_size = 1

    toc_window_end = sys.maxint

    # the last tocpage may be below the threshold, but is only kept if
    # it's above this
    trailing_tocpage_threshold = 1

    for page in pages:
		# XXX remove?
        if (len(page.info['number']) == 0
            and 'pageno_guess' in page.info):
            page.info['number'] = str(page.info['pageno_guess'])

        # skip on if we're waiting for a contents page
        if (len(tcs) == 0
            and contentscount > 0
            and page.info['type'] != 'contents'):
            continue
        if page.index < skip_pages_until_index:
            continue
        # l("%s: %s %s" % (page.index, page.info['number'],
        #                      page.info['type']))
        good_toc_count = 0
        for i, tc in enumerate(tcs):
            if windowed_match:
                if i < toc_window_start:
                    continue
                if i > toc_window_end:
                    continue
            tc.match_page(page)
            if tc.score > toc_threshold:
                toc_window_start = i
                if toc_window_end < toc_window_start + toc_window_size:
                    toc_window_end = toc_window_start + toc_window_size

        # append the current page as a toc candidate...
        # if contentscount is...
        # 0: build contents pages for first n pages
        # 2+: build contents pages exactly for designated pages
        # 1: skip pages before 1rst contents page, build n_optimistic pages, remember to score later pages
        if ((contentscount == 0 and len(tcs) < toc_count_to_try_if_no_contents_info)
            or (contentscount == 1 and len(tcs) < toc_count_to_try_if_contents_info)
            or (contentscount > 1 and len(tcs) < contentscount
                and page.info['type'] == 'contents')
            or (contents_leafs and page.index in contents_leafs)):
                tcs.append(TocCandidate(page))
        # break early if contents_leafs is around
        if contents_leafs and page.index - 1 in contents_leafs and not page.index in contents_leafs:
            break
        # support hardcode_toc_pages
        if contents_leafs and page.index in contents_leafs:
            tcs[-1].score = 10
        if not_contents_leafs and page.index in not_contents_leafs:
            tcs[-1].score = -10

    # adjust tc scores to promote trailing pages
    saw_good_score = False
    for i, tc in enumerate(tcs):
        tc.adj_score = tc.score
        if not saw_good_score:
            if tc.score > toc_threshold:
                saw_good_score = True
                continue
        if (tc.score < toc_threshold and
            tc.score > trailing_tocpage_threshold and
            i + 1 < len(tcs) and
            tcs[i + 1].score < toc_threshold):
            tc.adj_score = toc_threshold
            break

    # (for qdtoc algorithm)
    # Go through all tc candidates
    # - append to toc struct based on matches / nearno
    # - collect from tc: pageno cands = pageno_cands / pageno_cands_unfiltered
    all_pageno_cands = []
    for i, tc in enumerate(tcs):
        score = tc.score

        # if tc is not last, but *next* tc is below threshold,
        # accept if better than trailing_tocpage_threshold.
        if i + 1 < len(tcs):
            if (tcs[i + 1].score < toc_threshold and
                tc.score >= trailing_tocpage_threshold):
                score = toc_threshold

        if score >= toc_threshold:
            for match in tc.matches:
                info = tc.matchinfo[match]
                tocitem_words = info.matchwords()
                pagenum = info.nearno
                if info.nearno != -1:
                    pagenum = tc.words[pagenum]
                labelwords, titlewords = guess_label(tocitem_words)
                result['toc'].append({'level':1, 'label':(' '.join(labelwords)).strip(),
                                      'title':(' '.join(titlewords)).strip(), 'pagenum':pagenum,
                                      'tocpage':i
                                      })
            if i == 0:
                all_pageno_cands += tc.pageno_cands
            else:
                all_pageno_cands += tc.pageno_cands_unfiltered

    # pull sorted increasing set from pageno_cands - hopefully this'll
    # filter out chaff pagenos, as ToCs always have increasing page
    # numbers.
    if len(all_pageno_cands) > 0:
        all_pageno_cands_f = extract_sorted(all_pageno_cands)

        # create qdtoc:
        # loop through toc candidates and append qdtoc from each.
        most_recent_toc = 0
        for i, tc in enumerate(tcs):
            l(result, '%s %s' % (tc.page.index, tc.score))
            if tc.score > toc_threshold:
                good_toc_count += 1
                if good_toc_count >= max_allowed_toc_len:
                    failit(result, 'failed due to too many toc pages')
                    return result
                if most_recent_toc != 0:
                    if i >= most_recent_toc + 2:
                        failit(result, 'failed due to discontiguous tocs')
                        return result
                    most_recent_toc = i
                toc_els, tuple_toc_els = tc.get_qdtoc(all_pageno_cands_f)
                result['qdtoc'] += toc_els

        result['qdtoc'] = cleanup_toc(result['qdtoc'])
        check_toc(result)
    return result


# The below two functions look for increasing-by-1 sequences at the
# head of toc titles, and promote any matching words to the toc label
# XXX could do generic sequences a la 1-1.
def local_monotonic_p(seq):
    w = windowed_iterator(seq, 1)
    acceptable = 1
    for p in w:
        if p is 0:
            yield False
        diffs = 0
        expected = 0
        for n in w.neighbors(1):
            if n is not 0:
                diffs += abs(p - n)
                expected += 1
        if expected > 0 and diffs <= expected + acceptable:
            yield True
        else:
            yield False


def promote_leading_increasing_numeric_titlewords(toc):
    for ti in toc:
        if len(ti['title'].strip()) == 0:
            return
    splits = [ti['title'].split(None, 1) for ti in toc]
    def val_or_zero(v):
        v = re.sub(r'[:-]*$', '', v)
        v = v.strip()
        if v.isdigit():
            return int(v)
        return 0
    lms = local_monotonic_p((val_or_zero(s[0]) for s in splits))
    lma = [l for l in lms]
    for i, ti in enumerate(toc):
        if lma[i]:
            ti['label'] += ' ' + splits[i][0].strip()
            if len(splits[i]) > 1:
                ti['title'] = splits[i][1].strip()


def cleanup_toc(toc):
    if len(toc) > 1:
        if (toc[0]['pagenum'] == 'i' and
            toc[1]['pagenum'].isdigit()):
            toc[0]['pagenum'] = '1'
    
    for ti in toc:
        ti['title'] = re.sub(r'\s*[.\-\s_,]*\s*$', '', ti['title'])
    # promote_leading_increasing_numeric_titlewords(toc)

    # this would also be where simple struct inference based on e.g. part whatever happens.
    return toc


def check_toc(toc_result):
    # reject if:
    # - any title is too long.
    # - page numbers aren't monotonic
    # - some entries have pageno w/o title/label
    # - if toc pages skip
    # - if a toc item contains numbers?

    toc = toc_result['qdtoc']

    if len(toc) < 4:
        failit(toc_result, 'failed due to too short')
        return toc_result['isok']
    prevno = 0
    prevtocpage = toc[0]['tocpage']
    for ti in toc:
        titlewords = ti['title'].split()
        for i in range(len(titlewords)):
            titlewords[i] = titlewords[i].lower()
            if i > 4:
                if titlewords[i].isdigit():
                    failit(toc_result, 'suspected pagenum %s in title %s' %
                           (titlewords[i], ti['title']))
        for label in labels:
            if label in titlewords:
                failit(toc_result, 'failed due to label %s seen in "%s'
                       % (label, ti['title']))
        if len(ti['title']) > 80:
            failit(toc_result, 'failed due to too long title')
        if len(ti['title'].strip()) == 0 and len(ti['label'].strip()) == 0:
            failit(toc_result, 'failed due to empty title + label')
        rval = rnum_to_int(ti['pagenum'])
        if rval is 0:
            if int(ti['pagenum']) < prevno:
                failit(toc_result, 'non-monotonic pages in toc')
            prevno = int(ti['pagenum'])
        if ti['tocpage'] > prevtocpage + 1:
            failit(toc_result, 'skipped pages in toc')
        prevtocpage = ti['tocpage']
    return toc_result['isok']


labels = ('chapter', 'part', 'section', 'book',
          'preface', 'appendix', 'footnotes', 'epilog', 'epilogue'
          )
numbers = ('one', 'two', 'three', 'four', 'five',
           'six', 'seven', 'eight', 'nine', 'ten',
           'eleven', 'twelve', 'thirteen', 'fourteen', 'fifteen',
           'sixteen', 'seventeen', 'eighteen', 'nineteen', 'twenty',
           )


def guess_label(words):
    def cleanword(text):
        text = re.sub(r'[\s.:,\(\)\/;!\'\"\-]', '', text)
        text.strip()
        return text.lower()
    labelwords = []
    if len(words) > 1:
        w = cleanword(words[0])
        if w in labels:
            labelwords.append(words.pop(0))
            w = cleanword(words[0])
            if len(words) > 1 and (w.isdigit()
                                   or rnum_to_int(w) != 0
                                   or w in numbers):
                labelwords.append(words.pop(0))
        else:
            r = rnum_to_int(w)
            if r != 0:
                labelwords.append(words.pop(0))
    if len(labelwords) > 0:
        # strip trailing ':', etc, as they're now semantically redundant
        lastword = labelwords[-1]
        labelwords[-1] = re.sub(r'[.:\-,]*$', '', labelwords[-1])
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


# Used to handle toc entries that span pages
words_so_far = []
# parallel version for words-with-coordinates
wordtuples_so_far = []

class TocCandidate(object):
    def __init__(self, page):
        self.page = page
        self.matcher = SequenceMatcher()
        self.wordtuples = [word for word in page.get_words()]
        self.words = [word.text for word in self.wordtuples]
        self.rawwords = [word for word in page.get_words_raw()]

        # XXX MM DEBUG
#         self.words = [word.text for word in page.get_words_raw()]


        # self.words = [word.text for word in page.get_words()]
        # print self.words
        # for i in range(4):
        #     if i >= len(self.words):
        #         break
        #     # if i < len(self.words):
        #     #     self.words.pop(i)
        #     if self.words[i] == 'contents':
        #         self.words[i] = ''
        #     if self.words[i] == 'page':
        #         self.words[i] = ''
        self.wordhash = {}
        for word in self.words:
            self.wordhash[word] = True
        self.matcher.set_seq2(self.words)
        # l('\n'.join('%s:%s' % (i, w) for i, w in enumerate(self.words)))
        # l('content len: %s' % len(self.words))
        self.lookaside = {}
        self.pageno_cands = self.find_pageno_cands(filtered=True)
        self.pageno_cands_unfiltered = self.find_pageno_cands(filtered=False)
        self.matches = IntervalSet()
        self.matchinfo = {}
        self.score = 0
        self.adj_score = 0 # 'adjusted' score; as to boost last page in toc
        self.set_base_score()


    def set_base_score(self):
        if self.page.info['type'] == 'contents':
            self.score += 5
        labelcount = 1
        for i, w in enumerate(self.words):
            if w in labels:
                if i + 1 < len(self.words):
                    n = self.words[i + 1]
                    r = rnum_to_int(n)
                    if r != 0 or n.isdigit():
                        labelcount += 1
        if labelcount > 2:
            self.score += 5
                    

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

    def find_pageno_cands(self, filtered=True):
        """ Find the set of all numbers on this page that don't
        e.g. follow 'chapter', then find the largest increasing subset
        of these numbers; we consider it likely that these'll be book
        page numbers """
        # XXX i18n someday
        labels = ('chapter', 'part', 'section', 'book')
        if 'bounds' in self.page.info:
            bounds = self.page.info['bounds']
        else:
            bounds = self.page.find_text_bounds()
        xcutoff = bounds.l + (bounds.r - bounds.l) * PAGENO_X_RATIO
        def get_page_cands(page):
            # XXX mini stack to handle last-3 words ?
            lastword = ''

            for i, word in enumerate(self.wordtuples):
                box = word.box
                word = word.text
                if box.l < xcutoff or lastword in labels:
                    lastword = word
                    continue
                r = rnum_to_int(word)
                if r != 0:
                    yield pagenocand('0roman', r, i, self.page.index)
                for w in (word, # lastword + word
                          ):
                # for w in (word, lastword + word):
                    # XXX should add on-same-line check to above
                    # XXX this doesn't work currently, as it doesn't
                    # get reflected in output!
                    if w.isdigit():
                        val = int(w)
                        if val < 999:
                            # XXX replace above check with book page count
                            # if avail.
                            yield pagenocand('1arabic', int(w), i, self.page.index)
                lastword = word
        def printword(c):
            ar, val, loc = c
            print "%s %s - %s" % (ar, val, self.words[loc])
        page_cands = [c for c in get_page_cands(self.page)]

        result = page_cands

        if filtered and len(page_cands) > 0:
            extracted_orig = extract_sorted(page_cands)
            result = extracted_orig

        if filtered and less_greedy_heuristic:
            if len(page_cands) != 0:
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
        if FIRSTN != 0:
            words = [word.text for word in page.get_words()][:FIRSTN]
        else:
            words = [word.text for word in page.get_words()]
        for i, word in enumerate(words):
            words[i] = self.reify(word)
        self.matcher.set_seq1(words)
        page_matches = self.matcher.get_matching_blocks()
        page_matches.pop() # lose trailing informational not-a-match
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

    def get_qdtoc(self, all_pageno_cands, iabook):
        # pobj = abbyypage(page)
        valid_pages = {}
        for c in all_pageno_cands:
            if c.page_index == self.page.index:
                valid_pages[c.word_index] = c
        global words_so_far
        global wordtuples_so_far

        # flush accumulated words_so_far (possible wordy chapter
        # titles from previous pages) if too short, as it's then more
        # likely to be pagenos / noise
        if len(words_so_far) < 4:
            words_so_far = []
            wordtuples_so_far = []
        result = []
        tuple_result = []
        for i, word in enumerate(self.words):
            skipwords = ('table', 'of', 'contents', 'page', 'paob', 'chap')
            illustrationwords = ('illustrations',)
            if i < 5:
                l = word.lower()
                if l in illustrationwords:
                    return [],[]
                if l in skipwords:
                    continue
            if i in valid_pages:
                labelwords, titlewords = guess_label(words_so_far)
                ws = word.strip()

                pageindex = None
                pageleaf = None
                if ws in iabook.pageno_to_index_x_leafno:
                    pageindex, pageleaf = iabook.pageno_to_index_x_leafno[ws]

                level = iabook.marked_chapters_by_index.get(pageindex)
                if level is None:
#                     print >> sys.stderr, 'no marker found'
                    level = iabook.levels.index('chapter')
                else:
                    pass
#                     print >> sys.stderr, 'marker found'

                result.append({'level':level,
                               'label':(' '.join(labelwords)).strip(),
                               'title':(' '.join(titlewords)).strip(),
                               'pagenum':ws,
                               'pageindex':pageindex,
                               'pageleaf':pageleaf,
                               'tocindex':self.page.index,
                               'tocleaf':self.page.leafnum,
                               })
                tuple_result.append({'level':level,
                                     'title':wordtuples_so_far,
                                     'pagenum':ws, # self.wordtuples[i]
                                     'pageindex':pageindex,
                                     'pageleaf':pageleaf,
                                     'tocindex':self.page.index,
                                     'tocleaf':self.page.leafnum,
                                     })
                words_so_far = []
                wordtuples_so_far = []
            else:
                words_so_far.append(self.rawwords[i].text)
                wordtuples_so_far.append(self.wordtuples[i])
        return result, tuple_result
