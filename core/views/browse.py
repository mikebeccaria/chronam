import re, datetime, json, os, urlparse

from django import forms as django_forms

from django.conf import settings
from django.core.exceptions import ObjectDoesNotExist
from django.core.paginator import Paginator, InvalidPage
from django.core import urlresolvers
from django.forms import fields
from django.http import HttpResponse, HttpResponseNotFound, Http404, \
                        HttpResponseRedirect, HttpResponsePermanentRedirect
from django.shortcuts import render_to_response
from django.shortcuts import get_object_or_404
from django.template import RequestContext
from django.template.defaultfilters import filesizeformat
from django.utils import html, dateformat
from django.views.decorators.vary import vary_on_headers

from chronam.core.utils.url import unpack_url_path
from chronam.core import models, index
from chronam.core.index import SolrPaginator
from chronam.core.rdf import title_to_graph, issue_to_graph, page_to_graph

from chronam.core.utils.utils import HTMLCalendar, _get_tip, _stream_file, \
                                     _page_range_short, _rdf_base, get_page, \
                                     label, create_crumbs, get_month_list, get_year_list,get_all_dates_list
from chronam.core.decorator import cache_page, rdf_view


@cache_page(settings.DEFAULT_TTL_SECONDS)
def issues(request, lccn, year=None):
    title = get_object_or_404(models.Title, lccn=lccn)
    issues = title.issues.all()

    #determine whether issue is annual, monthly or daily and display calendar or list appropriately
    days = []
    months = []
    years = []
    for issue in issues:
        tmpyear, tmpmonth, tmpday = str(issue.date_issued).split('-')
        days.append(tmpday)
        months.append(tmpmonth)
        years.append(tmpyear)
        
    date_frequency = "yearly"
    for month in months:
        if month != "01":
            date_frequency = "monthly"
    for day in days:
        if day != "01":
            date_frequency = "daily"


    if issues.count() > 0:
        if year is None:
            _year = issues[0].date_issued.year
        else:
            _year = int(year)
    else:
        _year = 1900  # no issues available
    
    #year_view = HTMLCalendar(firstweekday=6, issues=issues).formatyear(_year)
    #print year_view
    #print settings.BROWSE_VIEW
    if settings.BROWSE_VIEW == "list":
        date_frequency = "list"
        #print "test"
    
    #print "date " + date_frequency
    
    if date_frequency == "list":
        cal_view = get_all_dates_list(issues, lccn)
        
    
    if date_frequency == "daily":
        
        cal_view = HTMLCalendar(firstweekday=6, issues=issues).formatyear(_year)
        dates = issues.dates('date_issued', 'year')
    
    if date_frequency == "monthly":
        
        cal_view = get_month_list(issues, lccn)

    if date_frequency == "yearly":
        cal_view = get_year_list(issues, lccn)

    #year_view = HTMLCalendar(firstweekday=6, issues=issues).formatyear(_year)
    #dates = issues.dates('date_issued', 'year')
    year_view = cal_view
    
    class SelectYearForm(django_forms.Form):
        year = fields.ChoiceField(choices=((d.year, d.year) for d in dates),
                              initial=_year)
    select_year_form = SelectYearForm()
    
    page_title = "Browse Issues: %s" % title.display_name
    page_name = "issues"
    crumbs = create_crumbs(title)
    return render_to_response('issues.html', dictionary=locals(),
                              context_instance=RequestContext(request))


@cache_page(settings.DEFAULT_TTL_SECONDS)
def title_holdings(request, lccn):
    title = get_object_or_404(models.Title, lccn=lccn)
    page_title = "Libraries that Have It: %s" % label(title)
    page_name = "holdings"
    crumbs = create_crumbs(title)

    holdings = title.holdings.select_related('institution').order_by('institution__name')

    return render_to_response('holdings.html', dictionary=locals(),
                              context_instance=RequestContext(request))


@cache_page(settings.DEFAULT_TTL_SECONDS)
def title_marc(request, lccn):
    title = get_object_or_404(models.Title, lccn=lccn)
    page_title = "MARC Bibliographic Record: %s" % label(title)
    page_name = "marc"
    crumbs = create_crumbs(title)
    return render_to_response('marc.html', dictionary=locals(),
                              context_instance=RequestContext(request))


@cache_page(settings.DEFAULT_TTL_SECONDS)
@rdf_view
def title_rdf(request, lccn):
    title = get_object_or_404(models.Title, lccn=lccn)
    graph = title_to_graph(title)
    response = HttpResponse(graph.serialize(base=_rdf_base(request),
                                            include_base=True),
                            mimetype='application/rdf+xml')
    return response


@cache_page(settings.DEFAULT_TTL_SECONDS)
def title_atom(request, lccn, page_number=1):
    title = get_object_or_404(models.Title, lccn=lccn)
    issues = title.issues.all().order_by('-batch__released', '-date_issued')
    paginator = Paginator(issues, 100)
    try:
        page = paginator.page(page_number)
    except InvalidPage:
        raise Http404("No such page %s for title feed" % page_number)

    # figure out the time the title was most recently updated
    # typically the release date of the batch, otherwise
    # when the batch was ingested
    issues = page.object_list
    num_issues = issues.count()
    if num_issues > 0:
        if issues[0].batch.released:
            feed_updated = issues[0].batch.released
        else:
            feed_updated = issues[0].batch.created
    else:
        feed_updated = title.created

    host = request.get_host()
    return render_to_response('title.xml', dictionary=locals(),
                              mimetype='application/atom+xml',
                              context_instance=RequestContext(request))


@cache_page(settings.DEFAULT_TTL_SECONDS)
def title_marcxml(request, lccn):
    title = get_object_or_404(models.Title, lccn=lccn)
    return HttpResponse(title.marc.xml, mimetype='application/marc+xml')


@cache_page(settings.DEFAULT_TTL_SECONDS)
def issue_pages(request, lccn, date, edition, page_number=1):
    title = get_object_or_404(models.Title, lccn=lccn)
    _year, _month, _day = date.split("-")
    try:
        _date = datetime.date(int(_year), int(_month), int(_day))
    except ValueError, e:
        raise Http404
    try:
        issue = title.issues.filter(date_issued=_date,
                                    edition=edition).order_by("-created")[0]
    except IndexError, e:
        raise Http404
    paginator = Paginator(issue.pages.all(), 20)
    try:
        page = paginator.page(page_number)
    except InvalidPage:
        page = paginator.page(1)
    page_range_short = list(_page_range_short(paginator, page))
    if not page.object_list:
        notes = issue.notes.filter(type="noteAboutReproduction")
        num_notes = notes.count()
        if num_notes >= 1:
            display_label = notes[0].label
            explanation = notes[0].text
    page_title = 'All Pages: %s, %s' % (label(title), label(issue))
    page_head_heading = "All Pages: %s, %s" % (title.display_name, label(issue))
    page_head_subheading = label(title)
    crumbs = create_crumbs(title, issue, date, edition)
    profile_uri = 'http://www.openarchives.org/ore/html/'
    response = render_to_response('issue_pages.html', dictionary=locals(),
                                  context_instance=RequestContext(request))
    return response


@cache_page(settings.DEFAULT_TTL_SECONDS)
@rdf_view
def issue_pages_rdf(request, lccn, date, edition):
    title, issue, page = _get_tip(lccn, date, edition)
    graph = issue_to_graph(issue)
    response = HttpResponse(graph.serialize(base=_rdf_base(request),
                                            include_base=True),
                            mimetype='application/rdf+xml')
    return response


@cache_page(settings.DEFAULT_TTL_SECONDS)
@vary_on_headers('Referer')
def page(request, lccn, date, edition, sequence, words=None):
    fragments = []
    if words:
        fragments.append("words=" + words)
    qs = request.META.get('QUERY_STRING')
    if qs:
        fragments.append(qs)
    if fragments:
        path_parts = dict(lccn=lccn, date=date, edition=edition,
                          sequence=sequence)
        url = urlresolvers.reverse('chronam_page',
                                   kwargs=path_parts)
        
        return HttpResponseRedirect(url + "#" + "&".join(fragments))

    title, issue, page = _get_tip(lccn, date, edition, sequence)

    if not page.jp2_filename:
        notes = page.notes.filter(type="noteAboutReproduction")
        num_notes = notes.count()
        if num_notes >= 1:
            explanation = notes[0].text
        else:
            explanation = ""

    # if no word highlights were requests, see if the user came
    # from search engine results and attempt to highlight words from their
    # query by redirecting to a url that has the highlighted words in it
    if not words:
        try:
            words = _search_engine_words(request)
            words = '+'.join(words)
            if len(words) > 0:
                path_parts = dict(lccn=lccn, date=date, edition=edition,
                                  sequence=sequence, words=words)
                url = urlresolvers.reverse('chronam_page_words',
                                           kwargs=path_parts)
                return HttpResponseRedirect(url)
        except Exception, e:
            if settings.DEBUG:
                raise e
            # else squish the exception so the page will still get
            # served up minus the highlights

    # Calculate the previous_issue_first_page. Note: it was decided
    # that we want to skip over issues with missing pages. See ticket
    # #383.
    _issue = issue
    while True:
        previous_issue_first_page = None
        _issue = _issue.previous
        if not _issue:
            break
        previous_issue_first_page = _issue.first_page
        if previous_issue_first_page:
            break

    # do the same as above but for next_issue this time.
    _issue = issue
    while True:
        next_issue_first_page = None
        _issue = _issue.next
        if not _issue:
            break
        next_issue_first_page = _issue.first_page
        if next_issue_first_page:
            break

    page_title = "%s, %s, %s" % (label(title), label(issue), label(page))
    page_head_heading = "%s, %s, %s" % (title.display_name, label(issue), label(page))
    page_head_subheading = label(title)
    crumbs = create_crumbs(title, issue, date, edition, page)

    filename = page.jp2_abs_filename
    if filename:
        try:
            im = os.path.getsize(filename)
            image_size = filesizeformat(im)
        except OSError:
            image_size = "Unknown"

    image_credit = issue.batch.awardee.name
    host = request.get_host()
    profile_uri = 'http://www.openarchives.org/ore/html/'
    template = "page.html"
    response = render_to_response(template, dictionary=locals(),
                                  context_instance=RequestContext(request))
    return response


@cache_page(settings.DEFAULT_TTL_SECONDS)
def titles(request, start=None, page_number=1):
    page_title = 'Newspaper Titles'
    if start:
        page_title += ' Starting With %s' % start
        titles = models.Title.objects.order_by('name_normal')
        titles = titles.filter(name_normal__istartswith=start.upper())
    else:
        titles = models.Title.objects.all().order_by('name_normal')
    paginator = Paginator(titles, 50)
    try:
        page = paginator.page(page_number)
    except InvalidPage:
        page = paginator.page(1)
    page_start = page.start_index()
    page_end = page.end_index()
    page_range_short = list(_page_range_short(paginator, page))
    browse_val = [chr(n) for n in range(65, 91)]
    browse_val.extend([str(i) for i in range(10)])
    collapse_search_tab = True
    crumbs = list(settings.BASE_CRUMBS)
    return render_to_response('titles.html', dictionary=locals(),
                              context_instance=RequestContext(request))


@cache_page(settings.DEFAULT_TTL_SECONDS)
def title(request, lccn):
    title = get_object_or_404(models.Title, lccn=lccn)
    page_title = "About %s" % label(title)
    page_name = "title"
    # we call these here, because the query the db, they are not
    # cached by django's ORM, and we have some conditional logic
    # in the template that would result in them getting called more
    # than once. Short story: minimize database hits...
    related_titles = title.related_titles()
    succeeding_titles = title.succeeding_titles()
    preceeding_titles = title.preceeding_titles()
    profile_uri = 'http://www.openarchives.org/ore/html/'
    notes = []
    has_external_link = False
    for note in title.notes.all():
        org_text = html.escape(note.text)
        text = re.sub('(http(s)?://[^\s]+[^\.])',
                      r'<a class="external" href="\1">\1</a>', org_text)
        if text != org_text:
            has_external_link = True
        notes.append(text)

    if title.has_issues:
        rep_notes = title.first_issue.notes.filter(type="noteAboutReproduction")
        num_notes = rep_notes.count()
        if num_notes >= 1:
            explanation = rep_notes[0].text

    # adding essay info on this page if it exists
    first_essay = title.first_essay
    first_issue = title.first_issue
    if first_issue:
        issue_date = first_issue.date_issued

    crumbs = create_crumbs(title)
    response = render_to_response('title.html', dictionary=locals(),
                                  context_instance=RequestContext(request))
    return response


@cache_page(settings.DEFAULT_TTL_SECONDS)
def titles_in_city(request, state, county, city,
                   page_number=1, order='name_normal'):
    state, county, city = map(unpack_url_path, (state, county, city))
    page_title = "Titles in City: %s, %s" % (city, state)
    titles = models.Title.objects.all()
    if city:
        titles = titles.filter(places__city__iexact=city)
    if county:
        titles = titles.filter(places__county__iexact=county)
    if state:
        titles = titles.filter(places__state__iexact=state)
    titles = titles.order_by(order)
    titles.distinct()

    if titles.count() == 0:
        raise Http404

    paginator = Paginator(titles, 50)
    try:
        page = paginator.page(page_number)
    except InvalidPage:
        page = paginator.page(1)
    page_range_short = list(_page_range_short(paginator, page))

    return render_to_response('reports/city.html', dictionary=locals(),
                              context_instance=RequestContext(request))


@cache_page(settings.DEFAULT_TTL_SECONDS)
def titles_in_county(request, state, county,
                     page_number=1, order='name_normal'):
    state, county = map(unpack_url_path, (state, county))
    page_title = "Titles in County: %s, %s" % (county, state)
    titles = models.Title.objects.all()
    if county:
        titles = titles.filter(places__county__iexact=county)
    if state:
        titles = titles.filter(places__state__iexact=state)
    titles = titles.order_by(order)
    titles = titles.distinct()

    if titles.count() == 0:
        raise Http404

    paginator = Paginator(titles, 50)
    try:
        page = paginator.page(page_number)
    except InvalidPage:
        page = paginator.page(1)
    page_range_short = list(_page_range_short(paginator, page))

    return render_to_response('reports/county.html', dictionary=locals(),
                              context_instance=RequestContext(request))


@cache_page(settings.DEFAULT_TTL_SECONDS)
def titles_in_state(request, state, page_number=1, order='name_normal'):
    state = unpack_url_path(state)
    page_title = "Titles in State: %s" % state
    titles = models.Title.objects.all()
    if state:
        titles = titles.filter(places__state__iexact=state)
    titles = titles.order_by(order)
    titles = titles.distinct()

    if titles.count() == 0:
        raise Http404

    paginator = Paginator(titles, 50)
    try:
        page = paginator.page(page_number)
    except InvalidPage:
        page = paginator.page(1)
    page_range_short = list(_page_range_short(paginator, page))

    return render_to_response('reports/state.html', dictionary=locals(),
                              context_instance=RequestContext(request))


# TODO: this redirect can go away some suitable time after 08/2010
# it predates having explicit essay ids
@cache_page(settings.DEFAULT_TTL_SECONDS)
def title_essays(request, lccn):
    title = get_object_or_404(models.Title, lccn=lccn)
    # if there's only one essay might as well redirect to it
    if len(title.essays.all()) >= 1:
        url = title.essays.all()[0].url
        return HttpResponsePermanentRedirect(url)
    else:
        return HttpResponseNotFound()


@cache_page(settings.DEFAULT_TTL_SECONDS)
def awardees(request):
    page_title = 'Awardees'
    awardees = models.Awardee.objects.all().order_by('name')
    return render_to_response('reports/awardees.html', dictionary=locals(),
                              context_instance=RequestContext(request))


@cache_page(settings.DEFAULT_TTL_SECONDS)
def awardee(request, institution_code):
    awardee = get_object_or_404(models.Awardee, org_code=institution_code)
    page_title = 'Awardee: %s' % awardee.name
    batches = models.Batch.objects.filter(awardee=awardee)
    return render_to_response('reports/awardee.html', dictionary=locals(),
                              context_instance=RequestContext(request))


def _search_engine_words(request):
    """
    Inspects the http request and returns a list of words from the OCR
    text relevant to a particular search engine query. If the
    request didn't come via a search engine result an empty list is
    returned.
    """
    # get the refering url
    referer = request.META.get('HTTP_REFERER')
    if not referer:
        return []
    uri = urlparse.urlparse(referer)
    qs = urlparse.parse_qs(uri.query)

    # extract a potential search query from refering url
    if 'q' in qs:
        words = qs['q'][0]
    elif 'p' in qs:
        qwords = qs['p'][0]
    else:
        return []

    # ask solr for the pre-analysis words that could potentially
    # match on the page. For example if we feed in 'buildings' we could get
    # ['building', 'buildings', 'BUILDING', 'Buildings'] depending
    # on the actual OCR for the page id that is passed in
    words = words.split(' ')
    words = index.word_matches_for_page(request.path, words)
    return words


@cache_page(settings.DEFAULT_TTL_SECONDS)
def page_ocr(request, lccn, date, edition, sequence):
    title, issue, page = _get_tip(lccn, date, edition, sequence)
    page_title = "%s, %s, %s" % (label(title), label(issue), label(page))
    crumbs = create_crumbs(title, issue, date, edition, page)
    host = request.get_host()
    return render_to_response('page_text.html', dictionary=locals(),
                              context_instance=RequestContext(request))


def page_pdf(request, lccn, date, edition, sequence):
    title, issue, page = _get_tip(lccn, date, edition, sequence)
    return _stream_file(page.pdf_abs_filename, 'application/pdf')


def page_png(request, lccn, date, edition, sequence):
    title, issue, page = _get_tip(lccn, date, edition, sequence)
    return _stream_file(page.jp2_abs_filename, 'image/png')


def page_ocr_xml(request, lccn, date, edition, sequence):
    title, issue, page = _get_tip(lccn, date, edition, sequence)
    return _stream_file(page.ocr_abs_filename, 'application/xml')



def page_ocr_txt(request, lccn, date, edition, sequence):
    title, issue, page = _get_tip(lccn, date, edition, sequence)
    try:
        text = page.ocr.text
        return HttpResponse(text, mimetype='text/plain')
    except models.OCR.DoesNotExist, e:
        raise Http404("No OCR for %s" % page)


@cache_page(settings.DEFAULT_TTL_SECONDS)
@rdf_view
def page_rdf(request, lccn, date, edition, sequence):
    page = get_page(lccn, date, edition, sequence)
    graph = page_to_graph(page)
    response = HttpResponse(graph.serialize(base=_rdf_base(request),
                                            include_base=True),
                            mimetype='application/rdf+xml')
    return response


@cache_page(settings.DEFAULT_TTL_SECONDS)
def page_print(request, lccn, date, edition, sequence,
               width, height, x1, y1, x2, y2):
    page = get_page(lccn, date, edition, sequence)
    title = get_object_or_404(models.Title, lccn=lccn)
    issue = page.issue
    page_title = "%s, %s, %s" % (label(title), label(issue), label(page))
    crumbs = create_crumbs(title, issue, date, edition, page)
    host = request.get_host()
    image_credit = page.issue.batch.awardee.name
    path_parts = dict(lccn=lccn, date=date, edition=edition,
                      sequence=sequence,
                      width=width, height=height,
                      x1=x1, y1=y1, x2=x2, y2=y2)
    url = urlresolvers.reverse('chronam_page_print',
                               kwargs=path_parts)

    return render_to_response('page_print.html', dictionary=locals(),
                              context_instance=RequestContext(request))


@cache_page(settings.DEFAULT_TTL_SECONDS)
def issues_first_pages(request, lccn, page_number=1):
    
    title = get_object_or_404(models.Title, lccn=lccn)
    issues = title.issues.all()
    if not issues.count() > 0:
        raise Http404("No issues for %s" % title.display_name)

    first_pages = []
    for issue in issues:
        first_pages.append(issue.first_page)

    paginator = Paginator(first_pages, 20)
    try:
        page = paginator.page(page_number)
    except InvalidPage:
        page = paginator.page(1)
    page_range_short = list(_page_range_short(paginator, page))

    page_title = 'Browse Issues: %s' % label(title)
    page_head_heading = "Browse Issues: %s" % title.display_name
    page_head_subheading = label(title)
    crumbs = create_crumbs(title)
    return render_to_response('issue_pages.html', dictionary=locals(),
                              context_instance=RequestContext(request))
