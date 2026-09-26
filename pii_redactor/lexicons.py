"""Word lists. Everything here is data; extend it without touching detector logic."""

# ---- detection side -------------------------------------------------------

# Given names that appear in the prospectus, plus the assignment's examples. Used only as an extra cue:
# <given name> + Capitalised word.
FIRST_NAMES = frozenset("""
ajay anand bharat dinesh ganesh gopal john jyoti kumar lalit lokesh prakash rajesh rashi rohan rohit
sachin shanti siddharth sunil tushar vijay amod sandesh sarthak varun eric peter
""".split())

STATES_AND_PLACES = frozenset(x.lower() for x in """
India Maharashtra Gujarat Pradesh Madhya Mumbai Pune Baner Chakan Khed Kurla Vikhroli Bandra
Churchgate Kanjurmarg Prabhadevi London Kingdom States America Bombay Virginia Georgia Emirates
""".split())

INDIAN_STATE_PATTERN = (
    r"Maharashtra|Gujarat|Karnataka|Kerala|Tamil\s+Nadu|Delhi|Goa|Punjab|Haryana|Rajasthan|Telangana|"
    r"Andhra\s+Pradesh|West\s+Bengal|Bihar|Odisha|Assam|Uttar\s+Pradesh|Madhya\s+Pradesh|Chhattisgarh|"
    r"Jharkhand|Uttarakhand|Himachal\s+Pradesh"
)

ADDRESS_WORDS = frozenset("""
floor tower building road rd marg street st avenue ave lane ln nagar park complex plot gat sector village
taluka wing block chowk colony society apartment apartments premises centre center estate industrial
farms off near next opp opposite behind highway hwy cross layout phase district dist west east north south
housing co-operative cooperative chambers hall hospital campus level main
""".split())

# Capitalised everyday words that must never be read as part of a person's name
# (glossary terms, units, currencies, months, ...). Grows with the documents you feed it.
_GLOSSARY_WORDS = frozenset("""
advanced chemistry cell basic custom duty bid lot circuit kilometers kilometres fractional horsepower indian
rupees liquid propane gas low tension high photo voltaic sitting fees swedish krona showroom underwriters
laboratories foundation house electricals motors industries enterprises associates traders holdings ventures
agencies technologies pradhan mantri awas yojana solar power energy steel copper aluminium wire cable
dated section chapter annexure schedule figure january february march april may june july august september
october november december monday tuesday wednesday thursday friday saturday sunday
""".split())

# Form-field labels ("Registered Office:", "Social Security Number:") are not names either.
_FORM_LABEL_WORDS = frozenset("""
registered corporate contact person social security number telephone tel mobile phone email address website
birth company customer ticket order invoice name title subject description status priority category reference
account billing shipping payment total amount balance summary details notes remarks comment comments
""".split())

NON_NAME_WORDS = _GLOSSARY_WORDS | _FORM_LABEL_WORDS

# Capitalised words that start many company names but are ordinary words on their own; never used
# as a stand-alone short name for a company ("Union Copper Rod LLC" must not turn "European Union" into a company).
GENERIC_CAPITALISED = frozenset("""
national central state federal union general global united first new royal standard precision advanced applied
international industrial electric power energy metal steel copper unit link open capital finance financial
investment leasing trading services solutions systems products group
""".split())

# A 6-digit number right after one of these words is a reference number, not a postal code.
NOT_A_PLACE_BEFORE_PIN = frozenset("""
no number id code pin pincode ref reference order ticket invoice account acct registration reg cin din
pan gstin isin folio client dp
""".split())

# Words that may appear lower-case *inside* an address segment.
ADDRESS_CONNECTORS = frozenset("of and to the no no. near opp".split())

# Words that introduce an address in running text ("... office located at 11/3, ..."): the address starts after them.
ADDRESS_LEAD_INS = frozenset("at in on is are was located situated address".split())

# Words that end an address when met while walking left (professional descriptions, ...).
ADDRESS_STOP_WORDS = frozenset("chartered accountants advocates solicitors auditors".split())

# Strong legal suffixes: a capitalised word run ending in one of these is a company.
# Plain words (spaces allowed); the detector turns them into Title Case / UPPER CASE regexes.
COMPANY_SUFFIXES = (
    "Private Limited", "Pvt Ltd", "Pvt. Ltd.", "Limited", "Ltd", "Ltd.", "LLP", "LLC", "Inc", "Inc.",
    "Corporation", "Corp", "Corp.", "Incorporated", "Trust", "PLC", "AB", "AG", "GmbH", "Pte Ltd", "Pty Ltd",
    "FZE", "FZCO", "Co.",
)

# Weak suffixes: ordinary business nouns. Only counted when the name before them is distinctive
# ("Kushal Electricals" yes, "Business Services" no).
COMPANY_WEAK_SUFFIXES = (
    "Electricals", "Motors", "Industries", "Enterprises", "Associates", "Traders", "Foundation",
    "Laboratories", "Showroom", "Technologies", "Holdings", "Ventures", "Agencies",
)

# Leading words that are never part of a company name even when Capitalised.
COMPANY_LEAD_STOP = frozenset(x.lower() for x in """
The Our Company Bid Offer Formerly Bidders Registrar Promoter Promoters Book Running Lead Managers
Syndicate Members Public Account Escrow Collection Sponsor Banks Bank Refund Short Term Long And Of
For With By To From In On At Between Among Certificate Certified Issued Statutory Auditors Auditors
Independent Chartered Accountants Peer Firm Named Namely Being Such Other Each All Any Vendor
Supplier Customer Client Employer Buyer Provider Issuer Lender Borrower
""".split())

# Public bodies (regulators, exchanges, depositories, government). Naming them
# does not identify anyone, so they are kept (precision choice, see README).
ORG_ALLOWLIST_KEYWORDS = (
    "securities and exchange board", "reserve bank", "bse limited", "national stock exchange", "nse",
    "national securities depository", "central depository", "national payments corporation",
    "registrar of companies", "stock exchange", "ministry", "government", "solar energy corporation",
    "life insurance corporation", "bombay stock", "depository", "insolvency",
)

# URL hosts that belong to regulators / exchanges / government and are kept.
URL_ALLOWLIST_SUFFIXES = (
    ".gov.in", "bseindia.com", "nseindia.com", "rbi.org.in", "npci.org.in", "nsdl.co.in", "cdslindia.com", "nic.in",
    "example.com",   # our own fake addresses
)

# ---- fake-value side ------------------------------------------------------

FAKE_FIRST = """
John Peter Mary James Emily Oliver Sophia Lucas Grace Henry Alice Ethan
Clara Felix Nora Owen Ruby Simon Tessa Victor Wendy Albert Bella Carter
Diana Edgar Fiona Gavin Hazel Isaac Julia Kyle Laura Marcus Nina Oscar
Paula Quinn Rosa Steven Tina Umar Vera Walter Xena Yusuf Zoe Adrian
Bianca Colin Daisy Elliot Freya Grant Holly Ivan Jasper Keira Leo Maya
Noel Opal Pierce Rhea Silas Thea Vince Abel Beatrice Caleb Delia Elias
Flora Gideon Harriet Ignatius Jonas Kara Lionel Mabel Nathan Olive Percy Rosalind
Stella Tobias Ursula Vernon Willa Xavier Yvette Zachary Agnes Barnaby Cecilia Dominic
Esme Franklin Gwen Hugo Imogen Joel Kirsten Lorne Melody Nigel Odette Phoebe
Reuben Selma Tristan Una Valerie Wesley Yara Zane Amelia Bruno Camille Dorian
Elsa Fergus Greta Hollis Iris Jude Kendra Lachlan Marlene Neville Orla Pascal
Rowan Sabine
""".split()

FAKE_LAST = """
Doe Parker Smith Turner Walker Hughes Bennett Carter Dawson Ellis Foster Graham
Harper Jensen Kent Lawson Morgan Nolan Owens Palmer Quincy Reed Sutton Thorne
Underwood Vaughn Wells Yates Zimmer Archer Bishop Cole Drake Emerson Fleming Grayson
Holland Irving Jordan Keller Lambert Mercer Norton Osborne Radcliffe Sinclair Tate Upton
Vance Whitaker Ashford Blackwell Crawford Donovan Everett Fairbanks Gallagher Hartley Ingram Jennings
Kirkland Langley Montgomery Nash Oakley Pemberton Quill Rutherford Stanton Thackeray Ulrich Voss
Winslow Yardley Zeller Abbott Barlow Chandler Dalton Eastwood Farrow Gilmore Hollister Ives
Jarvis Kendall Lockwood Marsh Newland Overton Prescott Rowland Sheridan Talbot Underhill Vickers
Wexford Yorke Ainsley Brandt Calloway Dunmore Ellison Fulton Garrison Hale Innes Kimball
Lowell Mallory Norwood
""".split()

FAKE_BRAND = """
Acme Brightwell Cobalt Dunmore Everly Fairmont Glenwood Harbor Ironwood Juniper Kestrel Lakeside
Meridian Northwind Oakridge Pinecrest Quartz Redwood Silverline Trident Umbra Vantage Willow Zephyr
Alder Beacon Cascade Delta Ember Falcon Granite Horizon Indigo Amberly Bluestone Copperfield
Driftwood Evergreen Foxglove Goldcrest Hawthorn Ivory Jadeite Kingfisher Larkspur Moonstone Nightingale Orchid
Paragon Quill Ravenwood Sandstone Thistle Uplands Violet Whitecap Yellowstone Ashgrove Birchwood Clearwater
Deepwell Elmhurst Frostline Greystone Highmark Ironbridge Jasmine Kensington Lionheart Millbrook Northgate Oakhaven
Pebblebrook Queensway Rosewood Stonebridge Tidewater Valebrook Westfield Windmere
""".split()

FAKE_NOUN = """
Holdings Industries Ventures Partners Systems Solutions Logistics Dynamics Enterprises Works
Trading Capital Networks Labs Group Resources Services
""".split()

FAKE_STREET = """
Maple Oak Cedar Pine Elm Willow Birch Sunset Lakeview Hillcrest Park Garden Church Mill River
Highland Meadow Orchard Station Market Bridge
""".split()

FAKE_CITY = """
Springfield Riverton Fairview Greenville Oakdale Lakewood Brookfield Ashland Milton Clifton
Georgetown Kingston Salem Madison Franklin
""".split()

FAKE_MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August",
               "September", "October", "November", "December"]
