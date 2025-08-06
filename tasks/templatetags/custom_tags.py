from django import template

register = template.Library()

@register.filter
def dict_get(dictionary, key):
    if isinstance(dictionary, dict):
        return dictionary.get(key, '')
    return ''

@register.filter
def user_has_role(participants, user):
    """
    Проверяет, есть ли у пользователя роль в задаче (например, исполнитель, наблюдатель).
    """
    return any(p.user == user for p in participants)
