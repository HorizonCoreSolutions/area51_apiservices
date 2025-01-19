import time
import traceback

from django.utils import timezone
from django.db import transaction as db_transaction
from django.db.models import F, Window
from django.db.models.functions import RowNumber
from django.core.management.base import BaseCommand

from apps.bets.utils import generate_reference
from apps.bets.models import CHARGED, CREDIT, DEBIT, Transactions
from apps.casino.models import Tournament, TournamentPrize, UserTournament
from apps.users.models import Users


class Command(BaseCommand):
    """
    Cron for distributing tournament prizes to registered users of that tournament. 
    If registered users count is less then minimum player required to start the tournament then refund will be processed.
    Users with higher balances receive higher ranks. If multiple users have the same balance, their ranks are 
    determined by the earliest update time of their last_win_at field. This ranking system follows a 
    "first come first serve" approach where users reaching the maximum balance first are ranked higher.
    """
    help = 'Distribute prize for the tournament'

    def handle(self, *args, **kwargs):
        try:
            while True:
                print("Tournament distribution starts")
                distrubute_prize = False
                current_date = timezone.now()
                tournaments = Tournament.objects.filter(end_date__lte=current_date, is_active=True, is_prize_distributed=False)
                for tournament in tournaments:
                    user_tournaments = tournament.usertournament_set.all()
                    if user_tournaments.count() >= tournament.min_player_limit:
                        distrubute_prize = True
                        self.tournament_prizes = tournament.tournamentprize_set.order_by("rank")

                        # Following code assigns ranks to users based on their point, prioritizing users with higher points. 
                        # In case of tied points, users are ranked based on the earliest 'last_win_at' update time.
                        user_tournaments = tournament.usertournament_set.filter(win_points__gt=0).annotate(
                            rank=Window(expression=RowNumber(),order_by=[F('win_points').desc(),"last_win_at"])
                        )[:self.tournament_prizes.count()]


                    operation = "Prize Distribution" if distrubute_prize else "Refund"
                    print(f"{operation} Start For The Tournament - {tournament.id}-{tournament.name}")
                    for user_tournament in user_tournaments:
                        if distrubute_prize:
                            self.distribute_tournament_prize(tournament, user_tournament)
                        else:
                            self.refund_tournament_registration_amount(user_tournament.user, tournament)
                        
                    tournament.is_prize_distributed = True
                    tournament.is_active = False
                    tournament.save()
                    print(f"{operation} End For The Tournament - {tournament.id}-{tournament.name}")
                print("Tournament distribution end")
                print('Sleep for 12 hours')
                time.sleep(43200)
        except Exception as e:
            print(traceback.format_exc())
            print(f"Error Tournament Prize Distribution: {e}")
            raise e
        
        
    def distribute_tournament_prize(self, tournament:Tournament, user_tournament:UserTournament):
        try:
            with db_transaction.atomic():
                user = user_tournament.user
                tournament_prize:TournamentPrize = self.tournament_prizes.filter(rank=user_tournament.rank).first()
                user_tournament.win_prize = tournament_prize.amount if tournament_prize.type == TournamentPrize.TournamentPrizeType.cash else tournament_prize.non_cash_prize
                user_tournament.save()

                if tournament_prize.type == TournamentPrize.TournamentPrizeType.cash:
                    previous_balance = user.balance
                    user.balance += tournament_prize.amount
                    user.save()

                    Transactions.objects.create(
                        user = user,
                        amount = tournament_prize.amount,
                        journal_entry = CREDIT,
                        status = CHARGED,
                        previous_balance = previous_balance,
                        new_balance = user.balance,
                        description = f'Tournament won by {user.username} - {tournament.name}',
                        reference = generate_reference(user),
                        bonus_type = "N/A",
                        bonus_amount = 0
                    )
                prize = tournament_prize.amount if tournament_prize.type=="cash" else tournament_prize.non_cash_prize
                print(f"Prize Distributed To User - {user.username}, Prize - {prize}")
        except Exception as e:
            print(traceback.format_exc())
            print(f"Error Prize Distribution for rank: {user_tournament.rank}, tournament: {tournament}, user_tournament: {user_tournament}, Error: {e}")
    
    
    def refund_tournament_registration_amount(self, user:Users, tournament:Tournament):
        try:
            description = f'Tournament registration by {user.username} - {tournament.id} : {tournament.name}'
            tournament_registration_transaction = Transactions.objects.filter(
                user = user,
                journal_entry = DEBIT,
                status = CHARGED,
                description = description,
            ).first()
            
            with db_transaction.atomic():
                previous_balance = user.balance
                user.balance += tournament_registration_transaction.amount
                user.save()

                Transactions.objects.create(
                    user = user,
                    amount = tournament_registration_transaction.amount,
                    journal_entry = CREDIT,
                    status = CHARGED,
                    previous_balance = previous_balance,
                    new_balance = user.balance,
                    description = f'Tournament refund - {tournament.name}',
                    reference = generate_reference(user),
                    bonus_type = "N/A",
                    bonus_amount = 0
                )
                print(f"Tournament Refund To User - {user.username}")
        except Exception as e:
            print(traceback.format_exc())
            print(f"Error Tournament Refund For User: {user.username}, tournament: {tournament} Error: {e}")

    
