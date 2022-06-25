import os
import ujson

from functools import partial
from colbert.utils.utils import print_message
from colbert.modeling.tokenization import QueryTokenizer, DocTokenizer, tensorize_triples

from colbert.utils.runs import Run

class valid_reader():
    def __init__(self, args, rank=0, nranks=1):
        # self.bsize, self.accumsteps = args.bsize, args.accumsteps

        self.query_tokenizer = QueryTokenizer(args.query_maxlen)
        self.doc_tokenizer = DocTokenizer(args.doc_maxlen)
        self.tensorize_triples = partial(tensorize_triples, self.query_tokenizer, self.doc_tokenizer)
        self.position = 0

        self.triples = self._load_triples(args.valid_triples, rank, nranks)
        self.queries = self._load_queries(args.valid_queries)
        self.collection = self._load_collection(args.collection)

    def _load_triples(self, path, rank, nranks):
        """
        NOTE: For distributed sampling, this isn't equivalent to perfectly uniform sampling.
        In particular, each subset is perfectly represented in every batch! However, since we never
        repeat passes over the data, we never repeat any particular triple, and the split across
        nodes is random (since the underlying file is pre-shuffled), there's no concern here.
        """
        print_message("#> Loading valid triples...")

        triples = []

        with open(path) as f:
            for line_idx, line in enumerate(f):
                if line_idx % nranks == rank:
                    qid, pos, neg = ujson.loads(line)
                    triples.append((qid, pos, neg))


        return triples

    def _load_queries(self, path):
        print_message("#> Loading valid queries...")

        queries = {}

        with open(path) as f:
            for line in f:
                qid, query = line.strip().split('\t')
                qid = int(qid)
                queries[qid] = query

        return queries


    # todo
    # 这个train和valid都加载了一次，重复！
    def _load_collection(self, path):
        print_message("#> Loading collection...")

        # collection = []
        collection = {}

        with open(path) as f:
            # print(path)
            for line_idx, line in enumerate(f):
                # print(line)
                # print(line_idx)
                pid, passage, title, *_ = line.strip().split('\t')

                # pid 是第几行的序号，对我们而言不是这样的
                # assert pid == 'id' or int(pid) == line_idx

                passage = title + ' | ' + passage
                # collection.append(passage)
                collection[int(pid)] = passage

        return collection

    def __iter__(self):
        return self

    def __len__(self):
        return len(self.triples)

    def __next__(self):
        offset, endpos = self.position, min(self.position + 1, len(self.triples))
        self.position = endpos
        # print(offset,endpos)

        if offset + 1 > len(self.triples):
            raise StopIteration

        queries, positives, negatives = [], [], []

        for position in range(offset, endpos):
            # print(position)
            query, pos, neg = self.triples[position]
            query, pos, neg = self.queries[query], self.collection[pos], self.collection[neg]

            queries.append(query)
            positives.append(pos)
            negatives.append(neg)

        return self.collate(queries, positives, negatives)

    def collate(self, queries, positives, negatives):
        # print(queries)
        # print(positives)
        # print(negatives)
        assert len(queries) == len(positives) == len(negatives) == 1
        return self.tensorize_triples(queries, positives, negatives, 1)

    # def skip_to_batch(self, batch_idx, intended_batch_size):
    #     Run.warn(f'Skipping to batch #{batch_idx} (with intended_batch_size = {intended_batch_size}) for training.')
    #     self.position = intended_batch_size * batch_idx