import os
import string
import spacy

from src.utils import helper

def list_files(startpath):
    for root, dirs, files in os.walk(startpath):
        level = root.replace(startpath, '').count(os.sep)
        indent = ' ' * 4 * (level)
        print('{}{}/'.format(indent, os.path.basename(root)))
        subindent = ' ' * 4 * (level + 1)
        for f in files:
            print('{}{}'.format(subindent, f))
            
            


MODEL_PATH = helper.get_path("models", "ner_model_Nov15")
print ("****Before****")
list_files(MODEL_PATH)
if not os.path.isfile(os.path.join(MODEL_PATH, "meta.json")):
    MODEL_PATH = os.path.join(MODEL_PATH, "ner_model_Nov15")
    print ("Moment of truth: " ,os.path.isfile(os.path.join(MODEL_PATH, "meta.json")))
    print("****After****")
    list_files(MODEL_PATH)
# BANK_DETS_MODEL_PATH = "bank_dets_model/ner_model"
BANK_DETS_MODEL_PATH = helper.get_path("models", "bank_dets_model_v3")
CREDIT_MEMO_MODEL_PATH = helper.get_path("models", "ner_model_credit_note_12_Mar_25")
TAPAL_NER_MODEL_PATH = helper.get_path("models", "ner_model_tapal_27Dec23")
CONTRACT_NUM_MODEL_PATH =  helper.get_path("models", "ner_model_contract_num_11_Mar_25")
ACCOUNT_NUM_MODEL_PATH = helper.get_path("models","ner_model_account_num_19Sept")
if not os.path.isfile(os.path.join(CREDIT_MEMO_MODEL_PATH, "meta.json")):
    CREDIT_MEMO_MODEL_PATH = os.path.join(CREDIT_MEMO_MODEL_PATH, "ner_model_credit_note_12_Mar_25")
if not os.path.isfile(os.path.join(TAPAL_NER_MODEL_PATH, "meta.json")):
    TAPAL_NER_MODEL_PATH = os.path.join(TAPAL_NER_MODEL_PATH, "ner_model_tapal_27Dec23")
if not os.path.isfile(os.path.join(CONTRACT_NUM_MODEL_PATH, "meta.json")):
    CONTRACT_NUM_MODEL_PATH = os.path.join(CONTRACT_NUM_MODEL_PATH, "ner_model_contract_num_11_Mar_25")
if not os.path.isfile(os.path.join(ACCOUNT_NUM_MODEL_PATH, "meta.json")):
    ACCOUNT_NUM_MODEL_PATH = os.path.join(ACCOUNT_NUM_MODEL_PATH, "ner_model_account_num_19Sept")
nlp = spacy.load(MODEL_PATH)#+"/ner_model")
nlp_bd = spacy.load(BANK_DETS_MODEL_PATH+"/ner_model")
nlp_cm = spacy.load(CREDIT_MEMO_MODEL_PATH)
nlp_tapal = spacy.load(TAPAL_NER_MODEL_PATH)
nlp_cn = spacy.load(CONTRACT_NUM_MODEL_PATH)
nlp_acn = spacy.load(ACCOUNT_NUM_MODEL_PATH)


# nlp = spacy.load(m_dir)


def predict(text):
    entities = {}
    translator = str.maketrans(string.punctuation, ' ' * len(string.punctuation))
    text = text.translate(translator)
    doc = nlp(text)
    # print(
    #     "SPACY"
    # )
    # print(doc)
    for ent in doc.ents:
        entities[ent.label_] = {'text': ent.text, 'start': ent.start_char}
    return entities


def predict_bank_details(text, entities_placeholder):
    # entities = {}
    translator = str.maketrans(string.punctuation, ' ' * len(string.punctuation))
    text = text.translate(translator)
    doc = nlp_bd(text)
    # print(
    #     "SPACY"
    # )
    # print(doc)
    print(doc.ents)
    for ent in doc.ents:
        if ent.label_ in entities_placeholder:
            entities_placeholder[ent.label_].append(ent.text)
    return entities_placeholder


def predict_credit_memo_num(text):
    text = text.replace("\r\n", " ").replace("\n", " ")
    doc = nlp_cm(text)
    if doc.ents:
        print("Predicted credit memo number: ", doc.ents)
        credit_memo_num = doc.ents[0].text
        if credit_memo_num[0] == "-":
            credit_memo_num = credit_memo_num[1:]
        return credit_memo_num
    return None


def predict_ntn_strn_num(text, tapal_placeholders):
    translator = str.maketrans(string.punctuation, ' ' * len(string.punctuation))
    text = text.translate(translator)
    doc = nlp_tapal(text)

    ntn_entities = []
    strn_entities = []

    if doc.ents:
        for ent in doc.ents:
            if ent.label_ in tapal_placeholders:
                if len(ent.text) < 10:
                    ntn_entities.append(ent.text.replace(' ', '-'))
                else:
                    strn_entities.append(ent.text.replace(' ', '-'))

    ntn_entities = list(dict.fromkeys(ntn_entities))
    tapal_placeholders["NTN"] = ntn_entities
    tapal_placeholders["STRN"] = strn_entities

    return tapal_placeholders

def predict_contract_num(text):
    text = text.replace("\r\n", " ").replace("\n", " ")
    doc = nlp_cn(text)
    if doc.ents:
        print("Predicted contract number: ", doc.ents)
        return doc.ents[0].text
    return None

def predict_account_num(text):
    text = text.replace("\r\n", " ").replace("\n", " ")
    doc = nlp_acn(text)
    if doc.ents:
        return doc.ents[0].text
    return None
# data_dir = "../../model/ner_model"
