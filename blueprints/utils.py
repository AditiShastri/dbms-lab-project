from models import ParkingLot

def get_user_sorted_lots(user):
    """
    Parses "1,3,2,4" from user preferences and returns ParkingLot objects in that order.
    """
    # 1. If no preferences, return default list
    if not user.preferences:
        return ParkingLot.query.all()
        
    # 2. Parse the string into a list of IDs
    try:
        pref_ids = [int(x) for x in user.preferences.split(',') if x.strip().isdigit()]
    except:
        return ParkingLot.query.all()
    
    # 3. Fetch all lots from DB
    all_lots = ParkingLot.query.all()
    
    # 4. Sort them based on the ID list
    # Create a dictionary for fast lookup: {1: LotObj, 2: LotObj...}
    lot_map = {lot.lot_id: lot for lot in all_lots}
    
    sorted_lots = []
    
    # Add lots in the user's specific order
    for pid in pref_ids:
        if pid in lot_map:
            sorted_lots.append(lot_map[pid])
            
    # Append any missing lots (e.g. if a new lot was added to DB but not in user prefs yet)
    for lot in all_lots:
        if lot not in sorted_lots:
            sorted_lots.append(lot)
            
    return sorted_lots

# --- 🧠 SMART PREFERENCE LOGIC ---
def get_default_preferences(dept):
    # IDs Mapping:
    # 1: CSE Ground
    # 2: Near Kotak
    # 3: Near RVU
    # 4: Near B Quad
    # 5: Mech Parking Lot (NEW!)
    
    dept = dept.upper()
    
    # CASE A: CS / IS / AIML 
    if dept in ['CSE', 'ISE', 'AIML', 'CS', 'IS']:
        return "1,2,3,5,4" 
        
    # CASE B: ECE / EEE / ETE 
    elif dept in ['ECE', 'EEE', 'ETE', 'EC', 'EE', 'ET']:
        return "1,3,4,5,2" 
        
    # CASE C: MECH / CIVIL / AERO / IEM 
    elif dept in ['MECH', 'CIVIL', 'AERO', 'IEM', 'ME', 'CV', 'AS', 'IM']:
        return "5,4,1,3,2" # Mech > RVU > B Quad...
        
    # CASE D: Default / Others (Prefer Central Locations)
    else: 
        return "4,5,1,2,3" # 