""" Retrieve documents from OpenAlex. We want 50 documents per subject in
our set, so all subjects have data. Process the titles and abstracts before
storing them. Keep also the document type and assigned subjects. Use the link
to the works found in subjects.json (works_api_url). Save 2000 documents per
file. """


import requests as req
import json
from collections import Counter
from os import listdir
import logging
from time import time

from flair.data import Sentence
from flair.tokenization import SpacyTokenizer
from flair.models import SequenceTagger

from nltk.stem import WordNetLemmatizer
from nltk.corpus import wordnet


class DocRetriever:
  def __init__(self, vocab_file):
    self.vocab = json.load(open(vocab_file))
    self.tokenizer = SpacyTokenizer('en_core_web_sm')
    self.lemmatizer = WordNetLemmatizer()
    self.tagger = SequenceTagger.load('upos-fast')
    self.tag_dict = {
      'ADJ': wordnet.ADJ,
      'NOUN': wordnet.NOUN,
      'VERB': wordnet.VERB,
      'ADV': wordnet.ADV
    }
  
  def get_docs(self, url, n=50):
    """ Given the URL leading to the documents of a subject, yield documents
    that are either publications. n is the number of docs that will be yielded. """
    yielded, page = 0, 1
    url += ',type:journal-article&page='
    while yielded < n:
      res = req.get(f'{url}{page}').json()
      if 'results' not in res:
        logging.error(f'No results: {res}')
        logging.info(f'{yielded} docs were found.')
        return
      logging.info(f'Fetched page {page}')
      for doc in res['results']:
        abstract = doc['abstract_inverted_index']
        if abstract is not None:
          yield {
            'data': self.process_texts(doc['display_name'], abstract),
            'subjects': {s['id']: s['score'] for s in doc['concepts']}
          }
          yielded += 1
          if yielded == n:
            logging.info(f'{yielded} docs were found.')
            return
      page += 1

  def process_texts(self, title, abstract_idx):
    """ Lower-case the string, lemmatize the words and remove those that don't
    appear in the vocab. Return the list of remaining words ordered by freq.
    and by order in the text when tied, without duplicates. Merge title and
    abstract after building the abstract from the index. """
    abstract = self.build_abstract(abstract_idx)
    if abstract[-2:] != '. ':
      abstract += '. '
    sentence = Sentence(abstract + title)
    self.tagger.predict(sentence)
    lemmas = []
    for token in sentence:
      if token.labels[0].value in self.tag_dict:
        lemmas.append(self.lemmatizer.lemmatize(
          token.text.lower(), self.tag_dict[token.labels[0].value])
        )
      else:
        lemmas.append(token.text.lower())
    lemmas_cnt = Counter(lemmas)
    vocab_lemmas = Counter()
    for word in lemmas_cnt:
      if word in self.vocab:
        vocab_lemmas[word] = lemmas_cnt[word]
    return [tup[0] for tup in vocab_lemmas.most_common()]
  
  def build_abstract(self, abstract_idx):
    """ Given an abstract as an inverted index, return it as normal text. """
    text = ''
    n_words = sum([len(v) for v in abstract_idx.values()])
    for i in range(n_words):
      for word in abstract_idx:
        if i in abstract_idx[word]:
          text += word + ' '
    return text
  

def main(vocab_file, subjects_file, n_docs=50, n_file=2000):
  """ Retrieve 'n_docs' docs for each subject and dump them in the folder
  'data/openalex/docs', with 'n_file' docs per file. n_docs should be a
  factor of n_file. We only check n_file after each subject is done. It can
  occur that a file has more than n_file docs, but never less. """
  retriever = DocRetriever(vocab_file)
  subjects = json.load(open(subjects_file))
  done = get_done_subjects()
  logging.info(f'{len(done)} subjects have been retrieved already.')
  batch = {}
  cnt, file_nr = 0, 1
  for subject, data in subjects.items():
    if subject in done:
      continue
    logging.info(f'Retrieving docs for {subject}')
    batch[subject] = []
    for doc in retriever.get_docs(data['works_api_url'], n_docs):
      batch[subject].append(doc)
    cnt += len(batch[subject])
    if cnt >= n_file:
      json.dump(batch, open(f'data/openalex/docs/{file_nr}.json', 'w'))
      file_nr += 1
      cnt = 0
      batch = {}
  if len(batch) > 0:
    json.dump(batch, open(f'data/openalex/docs/{file_nr}.json', 'w'))


def get_done_subjects():
  """ Return the subjects for which the documents have already been
  retrieved. They will be removed from the subject dict. """
  done = []
  for file in listdir('data/openalex/docs'):
    done += [s for s in json.load(open(f'data/openalex/docs/{file}'))]
  return done


if __name__ == '__main__':
  logging.basicConfig(
    level=logging.INFO,
    filename=f'logs/get_publications_{int(time())}.log'
  )
  vocab_file = 'data/vocab/vocab.json'
  subjects_file = 'data/openalex/subjects.json'
  main(vocab_file, subjects_file)