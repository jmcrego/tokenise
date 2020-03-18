
import logging
import yaml
import sys
import os
import io
import math
import glob
import gzip
import random
import itertools
import pyonmttok
import numpy as np
from collections import defaultdict, Counter

def open_file_read(file):
    logging.info('reading: {}'.format(file))
    if file.endswith('.gz'): 
        f = gzip.open(file, 'rb')
        is_gzip = True
    else: 
        f = io.open(file, 'r', encoding='utf-8', newline='\n', errors='ignore')
        is_gzip = False
    return f, is_gzip

####################################################################
### OpenNMTTokenizer ###############################################
####################################################################
class OpenNMTTokenizer():

    def __init__(self, fyaml):
        opts = {}
        if fyaml is None:
            self.tokenizer = None
        else:
            with open(fyaml) as yamlfile: 
                opts = yaml.load(yamlfile, Loader=yaml.FullLoader)

            if 'mode' not in opts:
                logging.error('error: missing mode in tokenizer')
                sys.exit()

            mode = opts["mode"]
            del opts["mode"]
            self.tokenizer = pyonmttok.Tokenizer(mode, **opts)
            logging.info('built tokenizer mode={} {}'.format(mode,opts))

    def tokenize(self, text):
        if self.tokenizer is None:
            tokens = text.split()
        else:
            tokens, _ = self.tokenizer.tokenize(text)
        return tokens

    def detokenize(self, tokens):
        if self.tokenizer is None:
            return tokens
        return self.tokenizer.detokenize(tokens)

####################################################################
### Vocab ##########################################################
####################################################################
class Vocab():

    def __init__(self):
        self.idx_unk = 0 
        self.str_unk = '<unk>'
        self.tok_to_idx = {} 
        self.idx_to_tok = [] 

    def read(self, file):
        f, is_gzip = open_file_read(file)
        for l in f:
            if is_gzip:
                l = l.decode('utf8')
            tok = l.strip(' \n')
            if tok not in self.tok_to_idx:
                self.idx_to_tok.append(tok)
                self.tok_to_idx[tok] = len(self.tok_to_idx)
        f.close()
        logging.info('read vocab ({} entries) from {}'.format(len(self.idx_to_tok),file))

    def dump(self, file):
        f = open(file, "w")
        for tok in self.idx_to_tok:
            f.write(tok+'\n')
        f.close()
        logging.info('written vocab ({} entries) into {}'.format(len(self.idx_to_tok),file))

    def build(self,files,token,min_freq=5,max_size=0):
        self.tok_to_frq = defaultdict(int)
        for file in files:
            f, is_gzip = open_file_read(file)
            for l in f:
                if is_gzip:
                    l = l.decode('utf8')                
                for tok in token.tokenize(l.strip(' \n')):
                    self.tok_to_frq[tok] += 1
            f.close()
        self.tok_to_idx[self.str_unk] = self.idx_unk
        self.idx_to_tok.append(self.str_unk)
        for wrd, frq in sorted(self.tok_to_frq.items(), key=lambda item: item[1], reverse=True):
            if len(self.idx_to_tok) == max_size:
                break
            if frq < min_freq:
                break
            self.tok_to_idx[wrd] = len(self.idx_to_tok)
            self.idx_to_tok.append(wrd)
        logging.info('built vocab ({} entries) from {}'.format(len(self.idx_to_tok),files))

    def __len__(self):
        return len(self.idx_to_tok)

    def __iter__(self):
        for tok in self.idx_to_tok:
            yield tok

    def __contains__(self, s): ### implementation of the method used when invoking : entry in vocab
        if type(s) == int: ### testing an index
            return s>=0 and s<len(self)
        ### testing a string
        return s in self.tok_to_idx

    def __getitem__(self, s): ### implementation of the method used when invoking : vocab[entry]
        if type(s) == int: ### input is an index, i want the string
            if s not in self:
                logging.error("key \'{}\' not found in vocab".format(s))
                sys.exit()
            return self.idx_to_tok[s]
        ### input is a string, i want the index
        if s not in self: 
            return self.idx_unk
        return self.tok_to_idx[s]

####################################################################
### Dataset ########################################################
####################################################################
class Dataset():

    def __init__(self, args, token, vocab, skip_subsampling=False):
        self.batch_size = args.batch_size
        self.window = args.window
        self.n_negs = args.n_negs
        self.vocab_size = len(vocab)
        self.idx_pad = vocab.idx_unk ### no need for additional token in vocab
        self.corpus = []
        self.wrd2n = defaultdict(int)
        ntokens = 0
        nOOV = 0
        for file in args.data:
            f, is_gzip = open_file_read(file)
            for l in f:
                if is_gzip:
                    l = l.decode('utf8')
                toks = token.tokenize(l.strip(' \n'))
                idxs = []
                for tok in toks:
                    idx = vocab[tok]
                    if idx == vocab.idx_unk:
                        nOOV += 1
                    idxs.append(idx)
                    self.wrd2n[idx] += 1
                self.corpus.append(idxs)
                ntokens += len(idxs)
            f.close()
        pOOV = 100.0 * nOOV / ntokens
        logging.info('read {} sentences with {} tokens (%OOV={:.2f})'.format(len(self.corpus), ntokens, pOOV))
        ### subsample
        if not skip_subsampling:
            ntokens = self.SubSample(ntokens)
            logging.info('subsampled to {} tokens'.format(ntokens))


        #'[batch_size={}, window={}, n_negs={}, skip_subsampling={}]'.format(self.batch_size,self.window,self.n_negs,self.skip_subsampling)


    def build_batchs(self):
        length = [len(self.corpus[i]) for i in range(len(self.corpus))]
        indexs = np.argsort(np.array(length))
        self.batchs = []
        batch_wrd = []
        batch_ctx = []
        batch_neg = []
        batch_snt = []
        batch_len = []
        for index in indexs:
            toks = self.corpus[index]
            if len(toks) < 2: ### may be subsampled
                continue

#            print('toks',toks)
            for i in range(len(toks)): #for each word in toks. Ex: 'a monster lives in my head'
                ### i=2 wrd=lives
                wrd = toks[i]
                batch_wrd.append(wrd)

                ### snt=[a, monster, in, my, head]
                snt = list(toks)
                del snt[i]
                batch_snt.append(snt)
                batch_len.append(len(snt))
                if len(batch_snt) > 1 and len(snt) > len(batch_snt[0]): ### add padding
                    for k in range(len(batch_snt)-1):
                        addn = len(batch_snt[-1]) - len(batch_snt[k])
                        batch_snt[k] += [self.idx_pad]*addn

                ### window=2, ctx=[a, monster, in, my]
                ctx = []
                for j in range(i-self.window,i+self.window+1):
                    if j<0:
                        ctx.append(self.idx_pad)
                    elif j>=len(toks):
                        ctx.append(self.idx_pad)
                    elif j!=i:
                        ctx.append(toks[j])
                batch_ctx.append(ctx)

                ### n_negs=4 neg=[over, last, today, virus]
                neg = []
                for _ in range(self.n_negs):
                    idx = random.randint(1, self.vocab_size-1)
                    while idx in ctx or idx == wrd:
                        idx = random.randint(1, self.vocab_size-1)
                    neg.append(idx)
                batch_neg.append(neg)

                if len(batch_wrd) == self.batch_size:
                    self.batchs.append([batch_wrd, batch_ctx, batch_neg, batch_snt, batch_len])
                    batch_wrd = []
                    batch_ctx = []
                    batch_neg = []
                    batch_snt = []
                    batch_len = []

        if len(batch_wrd):
            self.batchs.append([batch_wrd, batch_ctx, batch_neg, batch_snt, batch_len])

        logging.info('built {} batchs'.format(len(self.batchs)))
        del self.corpus
        del self.wrd2n


    def build_batchs_infer_sent(self):
        length = [len(self.corpus[i]) for i in range(len(self.corpus))]
        indexs = np.argsort(np.array(length))
        self.batchs = []
        batch_snt = []
        batch_len = []
        batch_ind = []
        for index in indexs:
            batch_snt.append(self.corpus[index])
            batch_len.append(batch_snt[-1])
            batch_ind.append(index)

            if len(batch_snt) == self.batch_size:
                self.batchs.append([batch_snt, batch_len, batch_ind])
                batch_snt = []
                batch_len = []
                batch_ind = []

        if len(batch_snt):
            self.batchs.append([batch_snt, batch_len, batch_ind])

        logging.info('built {} batchs'.format(len(self.batchs)))
        del self.corpus
        del self.wrd2n


    def __iter__(self):
        indexs = [i for i in range(len(self.batchs))]
        random.shuffle(indexs)
        for index in indexs:
            yield self.batchs[index]


    def SubSample(self, sum_counts):
#        wrd2n = dict(Counter(list(itertools.chain.from_iterable(self.corpus))))
        wrd2p_keep = {}
        for wrd in self.wrd2n:
            p_wrd = float(self.wrd2n[wrd]) / sum_counts ### proportion of the word
            p_keep = 1e-3 / p_wrd * (1 + math.sqrt(p_wrd * 1e3)) ### probability to keep the word
            wrd2p_keep[wrd] = p_keep

        filtered_corpus = []
        ntokens = 0
        for toks in self.corpus:
            filtered_corpus.append([])
            for wrd in toks:
                if random.random() < wrd2p_keep[wrd]:
                    filtered_corpus[-1].append(wrd)
                    ntokens += 1

        self.corpus = filtered_corpus
        return ntokens

    def NegativeSamples(self):
#        wrd2n = dict(Counter(list(itertools.chain.from_iterable(self.corpus))))
        normalizing_factor = sum([v**0.75 for v in self.wrd2n.values()])
        sample_probability = {}
        for wrd in self.wrd2n:
            sample_probability[wrd] = self.wrd2n[wrd]**0.75 / normalizing_factor
        words = np.array(list(sample_probability.keys()))
        probs = np.array(list(sample_probability.values()))
        while True:
            wrd_list = []
            sampled_index = np.random.multinomial(self.n_negs, probs)
            for index, count in enumerate(sampled_index):
                for _ in range(count):
                     wrd_list.append(words[index])
            yield wrd_list




