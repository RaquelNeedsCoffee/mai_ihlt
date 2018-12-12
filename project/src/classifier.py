import pandas as pd
import numpy as np
import csv
from os import listdir, path as pth, makedirs
from beautifultable import BeautifulTable

from scipy.stats import pearsonr
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.ensemble import RandomForestRegressor

from preprocessing import Preprocessor
from jaccard import Jaccard
import matplotlib.pyplot as plt
from mpl_toolkits.mplot3d import Axes3D

class Classifier:
    _GS_COLS = ['labels']
    _COLS = ['sentence0', 'sentence1']
    _DUMP_DIR = './dump'
    _DUMP_FILES = {
        'TRN': './dump/classifier.trn.dump',
        'TST': './dump/classifier.tst.dump',
        'PRE_TRN': './dump/classifier.pre_trn.dump',
        'PRE_TST': './dump/classifier.pre_tst.dump',
        'TRN_GS': './dump/classifier.trn_gs.dump',
        'TST_GS': './dump/classifier.tst_gs.dump'
    }

    def __init__(self, train_path, test_path):
        self.train_path = train_path
        self.test_path = test_path
        self.preprocessor = Preprocessor()
        self.trn = pd.DataFrame(columns=Classifier._COLS)       # Read data_frame
        self.tst = pd.DataFrame(columns=Classifier._COLS)       # Read data_frame
        self.trn_gs = pd.DataFrame(columns=Classifier._GS_COLS) # Known labels
        self.tst_gs = pd.DataFrame(columns=Classifier._GS_COLS) # Known labels
        self.pre_trn = pd.DataFrame(columns=Classifier._COLS)   # Preprocessed data_frame
        self.pre_tst = pd.DataFrame(columns=Classifier._COLS)   # Preprocessed data_frame
        self.vec_trn = []
        self.vec_tst = []

        self._dump_loaded = False

        self.jaccard = Jaccard()
        self.rfr = RandomForestRegressor(n_jobs=-1)
        self.vectorizer = TfidfVectorizer(max_features=None,
                                          strip_accents='unicode', analyzer='word', token_pattern=r'\w{1,}',
                                          ngram_range=(1, 3), use_idf=1, smooth_idf=1, sublinear_tf=1,
                                          stop_words='english')

        if not pth.exists(Classifier._DUMP_DIR):
            makedirs(Classifier._DUMP_DIR)

    # -------------------------------------------------- CLASSIFY ▼ ----------------------------------------------------

    def classify(self):
        print(self.trn.head())
        print('Preprocessing...')
        # If dump files where not loaded for first part of preprocessing, since this part is always the same
        if not self._dump_loaded:
            self.pre_trn = self.preprocessor.run_lemmas(self.trn)
            self.pre_tst = self.preprocessor.run_lemmas(self.tst)
            self.pre_trn = self.preprocessor.run_meaning(self.pre_trn)
            self.pre_tst = self.preprocessor.run_meaning(self.pre_tst)
            self.save_dump()

        self.vec_trn = self.vectorizer.fit_transform(self.pre_trn['sentence0'] + self.pre_trn['sentence1'])
        self.vec_tst = self.vectorizer.transform(self.pre_tst['sentence0'] + self.pre_tst['sentence1'])
        print(self.pre_trn.head())

        print('Training...')
        self.train_rfr()

        print('Testing...')
        predict_rfr_trn, predict_rfr_tst = self.test_rfr()
        predict_jac_trn, predict_jac_tst = self.test_jac()
        predict_vot_trn = self.voting(predict_rfr_trn, predict_jac_trn)
        predict_vot_tst = self.voting(predict_rfr_tst, predict_jac_tst)

        print('Done !')
        self.show_results(predict_rfr_trn, predict_rfr_tst, predict_jac_trn, predict_jac_tst, predict_vot_trn, predict_vot_tst)

    def voting(self, predict_rfr, predict_jac):
        voted = []
        for rfr, jac in zip(predict_rfr, predict_jac):
            if (rfr - jac) > -1.67:
                voted.append((0.55 * jac + rfr) / (1 + 0.55))
            else:
                voted.append((jac + 0.55 * rfr) / (1 + 0.55))
        return voted

    # --------------------------------------------------- MODELS ▼ ----------------------------------------------------

    # Random Forest Regression
    def train_rfr(self):
        self.rfr.fit(self.vec_trn, self.trn_gs.values.ravel())

    def test_rfr(self):
        return self.rfr.predict(self.vec_trn), self.rfr.predict(self.vec_tst)

    def test_jac(self):
        return self.jaccard.predict(self.pre_trn), self.jaccard.predict(self.pre_tst)

    # ---------------------------------------------------- SHOW ▼ -----------------------------------------------------

    def __add_table(self, table, name, trn, tst):
        table.append_column(name, [
            '{:.2f} std: {:.1f}'.format(np.mean(trn), np.std(trn)),
            '{:.2f} std: {:.1f}'.format(np.mean(tst), np.std(tst)),
            '{:.4f}'.format(pearsonr(trn, self.trn_gs['labels'])[0]),
            '{:.4f}'.format(pearsonr(tst, self.tst_gs['labels'])[0])
        ])

    def show_results(self, rfr_trn, rfr_tst, jac_trn, jac_tst, vot_trn, vot_tst):
        table = BeautifulTable()
        table.append_column('', ['Trn', 'Tst', 'Trn Pearson', 'Tst Pearson'])

        self.__add_table(table, 'Real', self.trn_gs['labels'], self.tst_gs['labels'])
        self.__add_table(table, 'RFR', rfr_trn, rfr_tst)
        self.__add_table(table, 'Jaccard', jac_trn, jac_tst)
        self.__add_table(table, 'Voting', vot_trn, vot_tst)
        plt.scatter(vot_tst, self.tst_gs['labels'], c='Blue')
        plt.xlabel('Voting label')
        plt.ylabel('Real label')
        plt.show()
        plt.scatter(jac_tst, self.tst_gs['labels'], c='Green')
        plt.xlabel('Jaccard label')
        plt.ylabel('Real label')
        plt.show()
        plt.scatter(rfr_tst, self.tst_gs['labels'], c='Red')
        plt.xlabel('RFR label')
        plt.ylabel('Real label')
        plt.show()
        print(table)
        self.show_worst_test(vot_tst, rfr_tst, jac_tst)

    def show_worst_test(self, predicted, predicted_rfr, predicted_jac, k=10):
        print('Worst results in voting:')
        err = np.abs(predicted - self.tst_gs['labels'].values)
        idx = np.argpartition(err, -k)[-k:]
        dic = {err[i]: i for i in idx}  # Create a dictionary with the errors as the key for sorting output
        for err in sorted(dic, reverse=True):
            i = dic[err]
            print(
                '\33[100m{:d} Predicted [Voting: {:.2f} RFR: {:.2f} Jaccard: {:.2f}] Target: {:.2f} Err: {:.2f}\033[0m\n  Original:     [{:s}] [{:s}]\n  Preprocessed: [{:s}] [{:s}]'
                .format(
                    i, predicted[i], predicted_rfr[i], predicted_jac[i], self.tst_gs['labels'].values[i], err,
                    str(self.tst['sentence0'].values[i]).replace('\n', '').replace('\r', ''),
                    str(self.tst['sentence1'].values[i]).replace('\n', '').replace('\r', ''),
                    str(self.pre_tst['sentence0'].values[i]),
                    str(self.pre_tst['sentence1'].values[i]),
                ))

    # --------------------------------------------------- LOADING ▼ ---------------------------------------------------

    def load(self, use_dump=True):

        #  (Try) Load from dump
        if use_dump:
            try:
                self.trn = pd.read_pickle(Classifier._DUMP_FILES['TRN'])
                self.tst = pd.read_pickle(Classifier._DUMP_FILES['TST'])
                self.trn_gs = pd.read_pickle(Classifier._DUMP_FILES['TRN_GS'])
                self.tst_gs = pd.read_pickle(Classifier._DUMP_FILES['TST_GS'])
                self.pre_trn = pd.read_pickle(Classifier._DUMP_FILES['PRE_TRN'])
                self.pre_tst = pd.read_pickle(Classifier._DUMP_FILES['PRE_TST'])
                self._dump_loaded = True
            except IOError:
                pass

        #  Load from txt files
        if not use_dump or not self._dump_loaded:
            self.trn, self.trn_gs = self.__load_all(self.train_path)
            self.tst, self.tst_gs = self.__load_all(self.test_path)

        print('Train: {0} Test: {1}'.format(self.trn.shape, self.tst.shape))

    def save_dump(self):
        self.trn.to_pickle(Classifier._DUMP_FILES['TRN'])
        self.tst.to_pickle(Classifier._DUMP_FILES['TST'])
        self.trn_gs.to_pickle(Classifier._DUMP_FILES['TRN_GS'])
        self.tst_gs.to_pickle(Classifier._DUMP_FILES['TST_GS'])
        self.pre_trn.to_pickle(Classifier._DUMP_FILES['PRE_TRN'])
        self.pre_tst.to_pickle(Classifier._DUMP_FILES['PRE_TST'])

    def __load_all(self, dir):
        files = listdir(dir)
        input = pd.DataFrame(columns=['sentence0', 'sentence1'])
        label = pd.DataFrame(columns=['labels'])
        for file in files:
            path = pth.join(dir, file)
            path_gs = path.replace('input', 'gs')
            if 'STS.input' in path:  # Only read input files
                input_df = pd.read_csv(path, sep='\t', lineterminator='\n', names=Classifier._COLS, header=None, quoting=csv.QUOTE_NONE)
                label_df = pd.read_csv(path_gs, sep='\t', lineterminator='\n', names=Classifier._GS_COLS, header=None, quoting=csv.QUOTE_NONE)
                input = input.append(input_df)
                label = label.append(label_df)

        return \
            input.fillna('').reset_index(drop=True), \
            label.fillna('').reset_index(drop=True)