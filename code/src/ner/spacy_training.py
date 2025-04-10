import os
import random
import string

import spacy
from spacy.training import Example

MODEL_DIR = "../../bank_dets_model"
if not os.path.isdir(MODEL_DIR):
    os.mkdir(MODEL_DIR)


ENTITIES = [
        "InvoiceNum",
        "PO",
        "InvoiceDate",
        "DueDate",
        "ABN"
    ]

BANK_DETAILS_ENTITIES = ["ABN", "AccountName", "AccountNum", "BankName", "BSB", "SwiftCode"]


def create_test_train_split(folder):

    files = os.listdir(folder)
    # files = [os.path.join(folder, fil) for fil in files]
    files = sorted(list(set([fil[:-4] for fil in files])))
    random.shuffle(files)

    train_folder = os.path.join(folder, "train")
    test_folder = os.path.join(folder, "test")
    if not os.path.isdir(train_folder):
        os.mkdir(train_folder)
    if not os.path.isdir(test_folder):
        os.mkdir(test_folder)

    split_point = int(len(files)*0.8)
    print("Training files: ", split_point)
    train_files = files[:split_point]
    test_files = files[split_point:]

    for fil in files:
        if fil in train_files:
            os.rename(os.path.join(folder, fil+".txt"), os.path.join(train_folder, fil+".txt"))
            os.rename(os.path.join(folder, fil+".ann"), os.path.join(train_folder, fil+".ann"))
        else:
            os.rename(os.path.join(folder, fil+".txt"), os.path.join(test_folder, fil+".txt"))
            os.rename(os.path.join(folder, fil+".ann"), os.path.join(test_folder, fil+".ann"))


def prepare_train_data(folder):
    files1 = os.listdir(folder)
    # files = [tf for tf in files if tf!="annotation.conf"]
    files1 = list(set([tf[:-4] for tf in files1]))

    data = []
    for tf in sorted(files1):
        entities_dict = {"entities": []}
        with open(os.path.join(folder, tf+".txt"), "r", encoding="mbcs") as f:
            text = f.read()
        with open(os.path.join(folder, tf+".ann"), "r") as f:
            annotation = f.readlines()
        for line in annotation:
            relevant_bit = line.split("\t")[1]
            ent, start, end = relevant_bit.split(" ")
            entities_dict["entities"].append((int(start), int(end), ent))
        data.append((text, entities_dict))
    random.shuffle(data)
    return data


def train(train_data, num_epochs=25):
    model_name = "ner_model"
    nlp = spacy.load("en_core_web_sm")

    # Getting the ner component
    ner = nlp.get_pipe('ner')

    for ent in ENTITIES:
        ner.add_label(ent)

    # Resume training
    optimizer = nlp.resume_training()
    move_names = list(ner.move_names)

    # List of pipes you want to train
    pipe_exceptions = ["ner", "trf_wordpiecer", "trf_tok2vec"]

    # List of pipes which should remain unaffected in training
    other_pipes = [pipe for pipe in nlp.pipe_names if pipe not in pipe_exceptions]

    for itn in range(num_epochs):
        for batch in spacy.util.minibatch(train_data, size=8):
            for text, annotations in batch:
                #             print(text[:10])
                #             print(annotations)
                losses = {}
                # create Example
                translator = str.maketrans(string.punctuation, ' ' * len(string.punctuation))
                text = text.translate(translator)
                doc = nlp.make_doc(text)
                example = Example.from_dict(doc, annotations)
                #             print(example)
                # Update the model
                nlp.update([example], losses=losses, drop=0.3)
                print("Losses", losses)

    nlp.to_disk(os.path.join(MODEL_DIR, model_name))
    return nlp


def evaluate_model(nlp, test_data):
    TP = 0
    TN = 0
    FP = 0
    FN = 0
    
    for tdata in TEST_DATA:
        text = tdata[0]
        doc = nlp(text)
        print("*"*100)
        actual_val = tdata[0][tdata[1]['entities'][0][0]:tdata[1]['entities'][0][1]]
        print("actual total: ", actual_val)
        # print(doc)
        found = False
        ent_found = False
        for ent in doc.ents:
            ent_found = True
    #         print(ent)
    #         print(type(ent))
            print(ent.text, ent.label_)
            if ent.text in actual_val:
                TP += 1
                found = True
                print("!!!")
                break
        if found is False and ent_found is False:
            FN += 1
        if found is False and ent_found is True:
            FP += 1
        
    accuracy = (TN+TP)/(TN+FP+FN+TP)
    precision = TP/(TP+FP)
    recall = TP/(TP+FN)
    f1_score = 2*((precision*recall)/(precision+recall))
    
    print("Trained model's accuracy is: ", accuracy)
    print("Trained model's precision is: ", precision)
    print("Trained model's recall is: ", recall)
    print("Trained model's F1 score is: ", f1_score)


create_test_train_split("../../data")
TRAIN_DATA = prepare_train_data("../../data/train")
trained_model = train(TRAIN_DATA)
