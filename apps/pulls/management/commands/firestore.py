# import firebase_admin
# from firebase_admin import credentials, firestore

# cred = credentials.Certificate("firebase.json")

# firebase_admin.initialize_app(cred)
# db = firestore.client()


# def set_event(event):
#     doc_ref = db.collection(u"d_event").document(str(event["FixtureId"]))
#     doc_ref.set(event)


# def set_event_with_imp_market(event):
#     doc_ref = db.collection(u"m_event").document(str(event["FixtureId"]) + "_main_markets")
#     doc_ref.set(event, merge=True)


# def get_imp_markets_from_firestore():
#     doc_ref = db.collection(u"imp_markets").document(u"markets")
#     return (doc_ref.get()).to_dict()


# def set_live_event(live_list):
#     doc_ref = db.collection(u"live_event").document("list")
#     doc_ref.set({"live_events": live_list})
    

# def get_live_event_list():
#     doc_ref = db.collection(u"live_event").document("list")
#     return (doc_ref.get()).to_dict()


# def update_event(event):
#     doc_ref = db.collection(u"d_event").document(str(event["FixtureId"]))
#     doc_ref.set(event, merge=True)


# def clear_events():
#     db.collection(u"d_event").set({})


# def get_list_of_fixtures():
#     docs = db.collection(u"d_event").stream()
#     fixtures = []
#     for doc in docs:
#         fixtures.append(str(doc.id))
#     return fixtures


# def delete_event(event_id):
#     try:
#         db.collection(u"d_event").document(event_id).delete()
#     except:
#         print("Error in deleting " + event_id)
#     try:
#         db.collection(u"m_event").document(event_id + "_main_markets").delete()
#     except:
#         print("Error in deleting " + event_id)


# def get_event_live(event_id):
#     try:
#         doc_ref = db.collection(u"d_event").document(str(event_id))
#         return (doc_ref.get()).to_dict()
#     except:
#         return {}


# # Methods for uploading prematch snapshots to firestore
# def set_event_prematch(event):
#     doc_ref = db.collection(u"p_event").document(str(event["FixtureId"]))
#     doc_ref.set(event)


# def get_event_prematch(event_id):
#     try:
#         doc_ref = db.collection(u"p_event").document(str(event_id))
#         return (doc_ref.get()).to_dict()
#     except:
#         return {}


# def set_prematch_event_list(pre_list):
#     doc_ref = db.collection(u"p_event_list").document("list")
#     doc_ref.set({"p_event_list": pre_list})


# def clear_prematch_events(event_id):
#     try:
#         db.collection(u"p_event").document(event_id).delete()
#     except:
#         print("Error in deleting " + event_id)


# def clear_prematch_event_list():
#     doc_ref = db.collection(u"p_event_list").document("list")
#     doc_ref.set({"p_event_list": []})


# def get_prematch_event_list():
#     doc_ref = db.collection(u"p_event_list").document("list")
#     return (doc_ref.get()).to_dict()


# def get_blacklist_event_list():
#     doc_ref = db.collection(u"blacklist_event").document("list")
#     return (doc_ref.get()).to_dict()


# def set_blacklist_event_list(event_list):
#     doc_ref = db.collection(u"blacklist_event").document("list")
#     doc_ref.set({"blacklist_event": event_list})


# def toogle_placing_bets(toogle_value):
#     doc_ref = db.collection(u"disable_bet").document("value")
#     toogle_value = True if (toogle_value.lower() == "true") else False
#     doc_ref.set({"value": toogle_value})


# def is_bet_disabled():
#     try:
#         doc_ref = db.collection(u"disable_bet").document("value")
#         return ((doc_ref.get()).to_dict())["value"]
#     except:
#         return False

