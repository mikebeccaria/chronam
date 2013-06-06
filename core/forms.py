import datetime

from django import forms
from django.forms import fields
from django.conf import settings
from django.core.cache import cache
from django.db.models import Min, Max

from chronam.core import models

MIN_YEAR = 1860
MAX_YEAR = 1922

FREQUENCY_CHOICES = (
    ("", "Select"),
    ("Daily", "Daily"),
    ("Three times a week", "Three times a week"),
    ("Semiweekly", "Semiweekly"),
    ("Weekly", "Weekly"),
    ("Biweekly", "Biweekly"),
    ("Three times a month", "Three times a month"),
    ("Semimonthly", "Semimonthly"),
    ("Monthly", "Monthly"),
    ("Other", "Other"),
    ("Unknown", "Unknown"),
)

PROX_CHOICES = (
    ("5", "5"),
    ("10", "10"),
    ("50", "50"),
    ("100", "100"),
)


def _titles_states():
    titles_states = cache.get("titles_states")
    if not titles_states:
        titles = [("", "All newspapers"),]
        countries = set()
        counties = set()
        towns = set()
        for title in models.Title.objects.filter(has_issues=True).select_related():
            short_name = title.name.split(":")[0]  # remove subtitle
            title_name = "%s (%s)" % (short_name,
                                      title.place_of_publication)
            titles.append((title.lccn, title_name))


            countries.add(title.country)
            towns.add(title.place_of_publication)
            places =  models.Place.objects.filter(titles=title)
            for place in places:
                counties.add(place.county)
        states = [("", "All states")]
        county_list = counties
        counties = [("", "All counties")]
        towns_list = towns
        towns = [("", "All Towns")]
       
        for country in countries:
            states.append((country.name, country.name))
        for county in county_list:
            counties.append((county,county))
        for town in towns_list:
            towns.append((town,town))
        counties = sorted(counties)
        states = sorted(states)
        towns = sorted(towns)
        print towns
        cache.set("titles_states", (titles, states, counties, towns))
    else:
        titles, states, counties, towns = titles_states
    return (titles, states, counties, towns)


def _fulltext_range():
    fulltext_range = cache.get('fulltext_range')
    if not fulltext_range:
        # get the maximum and minimum years that we have content for
        issue_dates = models.Issue.objects.all().aggregate(min_date=Min('date_issued'),
                                                           max_date=Max('date_issued'))

        # when there is no content these may not be set
        if issue_dates['min_date']:
            min_year = issue_dates['min_date'].year
        else:
            min_year = MIN_YEAR
        if issue_dates['max_date']:
            max_year = issue_dates['max_date'].year
        else:
            max_year = MAX_YEAR

        # removing these bits for https://rdc.lctl.gov/trac/chronam/ticket/1025
        # See: https://rdc.lctl.gov/trac/ndnp/ticket/446
        #min_year = max(min_year, MIN_YEAR)

        # I don't understand why... just doing what's asked. See:
        # https://rdc.lctl.gov/trac/ndnp/ticket/241
        #max_year = min(max_year, MAX_YEAR)

        fulltext_range = (min_year, max_year)
        cache.set('fulltext_range', fulltext_range)
    return fulltext_range


class SearchPagesForm(forms.Form):
    lccn = fields.ChoiceField(choices=[])
    state = fields.ChoiceField(choices=[])
    county = fields.ChoiceField(choices=[])
    town = fields.ChoiceField(choices=[])
    date1 = fields.ChoiceField(choices=[])
    date2 = fields.ChoiceField(choices=[])
    ortext = fields.CharField(widget=forms.widgets.TextInput(attrs ={"style":"width: 250px;"}))
    andtext = fields.CharField(widget=forms.widgets.TextInput(attrs ={"style":"width: 250px;"})) 
    phrasetext = fields.CharField(widget=forms.widgets.TextInput(attrs ={"style":"width: 250px;"}))
    proxtext = fields.CharField()
    proxdistance = fields.ChoiceField(choices=PROX_CHOICES)
    sequence = fields.BooleanField()
    year = fields.ChoiceField(choices=[])

    def __init__(self, *args, **kwargs):
        super(SearchPagesForm, self).__init__(*args, **kwargs)
        self.titles, self.states, self.counties, self.towns = _titles_states()
        

        fulltextStartYear, fulltextEndYear = _fulltext_range()

        self.years = [(year, year) for year in range(fulltextStartYear, fulltextEndYear + 1)]
        self.fulltextStartYear = fulltextStartYear
        self.fulltextEndYear = fulltextEndYear

        self.fields["ortext"].widget.attrs["class"] = "ortext"
        self.fields["proxtext"].widget.attrs["alt"] = "proxtext"
        self.fields["lccn"].widget.attrs = {'style':'width: 300px'}
        self.fields["lccn"].choices = self.titles
        self.fields["state"].choices = self.states
        self.fields["state"].widget.attrs = {'alt': 'id_state', 'style':'width: 140px'}
        self.fields["county"].choices = self.counties
        self.fields["county"].widget.attrs = {'alt': 'id_county', 'style':'width: 140px'}
        self.fields["town"].choices = self.towns
        self.fields["town"].widget.attrs = {'alt': 'id_town', 'style':'width: 140px'}
        self.fields["date1"].choices = self.years 
        self.fields["date1"].initial = fulltextStartYear
        self.fields["date1"].widget.attrs["class"] = "norm"
        self.fields["date2"].choices = self.years
        self.fields["date2"].initial = fulltextEndYear
        self.fields["date2"].widget.attrs["class"] = "norm"
        self.fields["year"].choices = self.years
        self.fields["sequence"].widget.attrs['value'] = 1
        self.fields["sequence"].widget.attrs['value'] = 1
        

        
class AdvSearchPagesForm(SearchPagesForm):
    lccn = fields.MultipleChoiceField(choices=[])
    state = fields.MultipleChoiceField(choices=[])
    county = fields.MultipleChoiceField(choices=[])
    town = fields.MultipleChoiceField(choices=[])
    date1 = fields.CharField()
    date2 = fields.CharField()
    sequence = fields.CharField()
    ortext = fields.CharField()
    andtext = fields.CharField()
    phrasetext = fields.CharField()
    proxtext = fields.CharField()
    proxdistance = fields.ChoiceField(choices=PROX_CHOICES)
    language = fields.ChoiceField()

    def __init__(self, *args, **kwargs):
        super(AdvSearchPagesForm, self).__init__(*args, **kwargs)

        self.titles, self.states, self.counties, self.towns = _titles_states()
        
        fulltextStartYear, fulltextEndYear = _fulltext_range()

        years = [(year, year) for year in range(fulltextStartYear, fulltextEndYear+1)]
        
        self.fulltextStartYear = fulltextStartYear
        self.fulltextEndYear = fulltextEndYear
        self.date = self.data.get('date1', '')

        self.fields["lccn"].widget.attrs = {'id':'id_lccns', 'style':'width: 350px', 'size':'8'}
        self.fields["lccn"].choices = self.titles
        self.fields["county"].choices = self.counties
        self.fields["county"].widget.attrs = {'alt': 'id_county', 'style':'width: 140px'}
        self.fields["state"].choices = self.states
        self.fields["state"].widget.attrs = {'id':'id_states','style':'width: 140px', 'size':'8'}
        self.fields["town"].choices = self.towns
        self.fields["town"].widget.attrs = {'alt': 'id_town', 'style':'width: 140px', 'size':'8'}

        self.fields["date1"].choices = self.years 
        self.fields["date1"].widget.attrs = {"class":"txt", "id":"id_datefrom", "style":"width:70px;", "max_length":10, }
        self.fields["date2"].choices = self.years
        self.fields["date2"].widget.attrs = {"class":"txt", "id":"id_dateto", "style":"width:70px;", "max_length":10, }

        self.fields["sequence"].widget.attrs = {"id":"id_char_sequence", "alt": "char_sequence", "size":"3"}
        self.fields["proxtext"].widget.attrs["id"] = "id_proxtext_adv"

        self.fields["proxtext"].widget.attrs["id"] = "id_proxtext_adv"
        lang_choices = [("", "All"), ]
        lang_choices.extend((l, models.Language.objects.get(code=l).name) for l in settings.SOLR_LANGUAGES)
        self.fields["language"].choices = lang_choices


class SearchTitlesForm(forms.Form):
    state = fields.ChoiceField(choices=[], initial="")
    county = fields.ChoiceField(choices=[], initial="")
    city = fields.ChoiceField(choices=[], initial="")
    year1 = fields.ChoiceField(choices=[], label="from")
    year2 = fields.ChoiceField(choices=[], label="to")
    terms = fields.CharField(max_length=255)
    frequency = fields.ChoiceField(choices=FREQUENCY_CHOICES, initial="", label="Frequency:")
    language = fields.ChoiceField(choices=[], initial="", label="Language:")
    ethnicity = fields.ChoiceField(choices=[], initial="", label="Ethnicity Press:")
    labor = fields.ChoiceField(choices=[], initial="", label="Labor Press:")
    material_type = fields.ChoiceField(choices=[], initial="", label="Material Type:")
    lccn = fields.CharField(max_length=255, label="LCCN:")

    def __init__(self, *args, **kwargs):
        super(SearchTitlesForm, self).__init__(*args, **kwargs)
        current_year = datetime.date.today().year
        years = range(1690, current_year + 1, 10)
        if years[-1] != current_year:
            years.append(current_year)
        choices = [(year, year) for year in years]
        self.fields["year1"].choices = choices
        self.fields["year1"].widget.attrs["class"] = "norm"
        self.fields["year1"].initial = choices[0][0]
        self.fields["year2"].choices = choices
        self.fields["year2"].initial = choices[-1][0]
        self.fields["year2"].widget.attrs["class"] = "norm"

        language = [("", "Select"), ]
        language.extend((l.name, l.name) for l in models.Language.objects.all())
        self.fields["language"].choices = language

        ethnicity = [("", "Select"), ]
        ethnicity.extend((e.name, e.name) for e in models.Ethnicity.objects.all())
        self.fields["ethnicity"].choices = ethnicity

        labor = [("", "Select"), ]
        labor.extend((l.name, l.name) for l in models.LaborPress.objects.all())
        self.fields["labor"].choices = labor

        material = [("", "Select")]
        material.extend((m.name, m.name) for m in models.MaterialType.objects.all())
        self.fields["material_type"].choices = material
