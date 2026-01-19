from djchoices import ChoiceItem, DjangoChoices

class Coins(DjangoChoices):
    SC = ChoiceItem("sc", "SC")
    GC = ChoiceItem("gc", "GC")
    MC = ChoiceItem("mc", "MC")

def coin_matches(coin_value, coin_choice):
    """
    Compares a value from the database (e.g. "sc") with a Coins choice,
    or checks if a verbose name ("SC") matches the choice verbose name.
    """
    # coin_choice is a Coins class member such as Coins.SC
    return coin_value == coin_choice or coin_value == coin_choice.value or coin_value == coin_choice.display
