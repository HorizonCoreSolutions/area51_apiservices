
from django import template


register = template.Library()


@register.filter
def is_active(link, url):
    if link == 'composite' and url[:18] == '/surveys/composite':
        return 'active'
    elif link != 'composite' and url[:18] == '/surveys/composite':
        return ''
    elif link == 'settings':

        # TODO add another pages
        if url == '/import/' or url[:26] == '/surveys/preferred_scopes/' or url[:23] == '/surveys/aging_factors/' \
                or '/accounts/company_user' in url:
            return 'active'
        else:
            return ''
    elif link == 'company_users' and '/accounts/company_user' in url:
        return 'active'
    elif link == 'survey_settings' and (
            url[:26] == '/surveys/preferred_scopes/' or url[:23] == '/surveys/aging_factors/'):
        return 'active'
    elif link == 'preferred' and url[:26] == '/surveys/preferred_scopes/':
        return 'active'
    elif link == 'factors' and url[:23] == '/surveys/aging_factors/':
        return 'active'
    elif link == 'standard' and url[:23] == '/reports/standard/':
        return 'active'
    elif link == 'report_view' and url[:23] == '/reports/report_view/':
        return 'active'
    elif link == 'report_design' and url[:23] == '/reports/report_design/':
        return 'active'

    else:
        new_url = url[1:]
        slash_pos = new_url.find('/')
        new_url = url[1:int(slash_pos) + 1]

        if url[:26] == '/surveys/preferred_scopes/' or url[:23] == '/surveys/aging_factors/':
            return ''

        if link == new_url:
            return 'active'
        else:
            return ''


@register.filter
def pagination_url_replace(page, request):
    """
    Add other GET params to the Url on pagination
    :param page: page number
    :param request: current request
    :return: new url
    """

    dict_ = request.GET.copy()
    dict_['page'] = page

    return dict_.urlencode()
