import os
import sys
import time
import datetime
import re
from pathlib import Path
from tqdm import tqdm
from copy import deepcopy, copy
import traceback
import pickle
import random
from collections import Counter, defaultdict
import warnings
import gc

import numpy as np
import pandas as pd

import matplotlib.pyplot as plt
import matplotlib.cm as colormap
import seaborn as sns

# from catboost import CatBoostRegressor, CatBoostClassifier, Pool
# from lightgbm import LGBMRegressor, LGBMClassifier, Dataset
from sklearn.ensemble import RandomForestRegressor, RandomForestClassifier
from sklearn.linear_model import LinearRegression, LogisticRegression, Ridge, Lasso
from sklearn.metrics import roc_auc_score
from sklearn.calibration import calibration_curve, CalibratedClassifierCV

try:
    import category_encoders as ce
    EXT_CE = True
except:
    EXT_CE = False
from .preprocessing import CatEncoder
from .metrics import RMSE


'''
Training automation
'''

class Trainer:
    '''
    Make machine learning easy again!

    # Usage
    model = Trainer(CatBoostClassifier(**CAT_PARAMS))
    model.train(x_train, y_train, x_valid, y_valid, fit_params={})
    '''
    MODELS = {
        'CatBoostRegressor', 'CatBoostClassifier', 
        'LGBMRegressor', 'LGBMClassifier',
        'RandomForestRegressor', 'RandomForestClassifier', 
        'LinearRegression', 'LogisticRegression', 
        'Ridge', 'Lasso',
        'SVR', 'SVC',
    }

    def __init__(self, model):
        model_type = type(model).__name__
        assert model_type in self.MODELS

        self.model = model
        self.model_type = model_type
        self.is_trained = False
        self.null_importances = None
        self.permutation_importances = None
        self.cal_model = None
    
    def train(self, X, y, 
              X_valid=None, y_valid=None, 
              categorical_features=None, cat_features=None, fit_params={}, 
              calibration=False, calibration_params={'method': 'isotonic', 'cv': 3}):

        if cat_features is None and categorical_features is not None:
            cat_features = categorical_features
        elif cat_features is not None and categorical_features is not None:
            print('cat_features and categorical_features conflicts. cat_features will be ignored.')
            cat_features = categorical_features
        self.input_shape = X.shape

        if self.model_type[:8] == 'CatBoost':
            train_data = Pool(data=X, label=y, cat_features=cat_features)
            if X_valid is not None:
                valid_data = Pool(data=X_valid, label=y_valid, cat_features=cat_features)
            else:
                valid_data = Pool(data=X, label=y, cat_features=cat_features)
            self.model.fit(X=train_data, eval_set=valid_data, **fit_params)
            self.best_iteration = self.model.get_best_iteration()

        elif self.model_type[:4] == 'LGBM':
            if cat_features is None:
                cat_features = []
            if X_valid is not None:
                self.model.fit(X, y, eval_set=[(X, y), (X_valid, y_valid)], 
                            categorical_feature=cat_features, **fit_params)
            else:
                self.model.fit(X, y, eval_set=[(X, y)],
                               categorical_feature=cat_features, **fit_params)
            self.best_iteration = self.model.best_iteration_

        else:
            self.model.fit(X, y, **fit_params)
            self.best_iteration = 0

        self.is_trained = True

        if calibration:
            self.cal_model = CalibratedClassifierCV(self.model, **calibration_params)
            self.cal_model.fit(X, y)

    def get_model(self):
        return self.model

    def get_best_iteration(self):
        return self.best_iteration

    def predict(self, X, method='predict'):
        if X is None:
            print('No data to predict.')
            return None
        if self.cal_model is None:
            _model = self.model
        else:
            _model =  self.cal_model

        if method == 'predict':
            return _model.predict(X)
        elif method == 'binary_proba':
            return _model.predict_proba(X)
        elif method == 'binary_proba_positive':
            return _model.predict_proba(X)[:, 1]
        else:
            raise ValueError(method)

    def get_feature_importances(self, method='fast', importance_params={}):
        if method == 'auto':
            if self.model_type in ['CatBoostRegressor', 'CatBoostClassifier',
                                   'LGBMRegressor', 'LGBMClassifier',
                                   'RandomForestRegressor', 'RandomForestClassifier']:
                return self.model.feature_importances_
            else:
                if self.permutation_importances is None:
                    return self.get_permutation_importances(**importance_params)
                else:
                    return self.permutation_importances
        elif method == 'fast':
            if self.model_type in ['CatBoostRegressor', 'CatBoostClassifier',
                                   'LGBMRegressor', 'LGBMClassifier',
                                   'RandomForestRegressor', 'RandomForestClassifier']:
                return self.model.feature_importances_
            else: # Gomennasai
                return np.zeros(self.input_shape[1])
        elif method == 'permutation':
            if self.permutation_importances is None:
                return self.get_permutation_importances(**importance_params)
            else:
                return self.permutation_importances
        elif method == 'null':
            if self.null_importances is None:
                return self.get_null_importances(**importance_params)
            else:
                return self.null_importances
        else:
            raise ValueError(method)

    def get_null_importances(self, X, y, X_valid=None, y_valid=None,
                            cat_features=None, fit_params={}, prediction='predict',
                            eval_metric=None, iteration=10, verbose=False):
        assert self.model_type in ['CatBoostRegressor', 'CatBoostClassifier',
                                   'LGBMRegressor', 'LGBMClassifier',
                                   'RandomForestRegressor', 'RandomForestClassifier']
        assert self.is_trained

        if verbose:
            _iter = tqdm(range(iteration), desc='Calculating null importance')
        else:
            _iter = range(iteration)

        # Get actual importances
        actual_imps = self.model.feature_importances_
        null_imps = np.empty(
            (iteration, self.input_shape[1]), dtype=np.float16)

        # Get null importances
        for i in _iter:
            y_shuffled = np.random.permutation(y)
            self.train(X, y_shuffled, X_valid, y_valid,
                       cat_features, fit_params)
            null_imps[i] = self.model.feature_importances_

        # Calculation feature score
        null_imps75 = np.percentile(null_imps, 75, axis=0)
        null_importances = np.log(1e-10 + actual_imps / (1 + null_imps75))
        self.null_importances = null_importances
        return null_importances

    def get_permutation_importances(self, X, y, X_valid=None, y_valid=None,
                                   cat_features=None, fit_params={}, pred_method='predict', 
                                   eval_metric=RMSE(), iteration=None, verbose=False):
        assert self.is_trained

        if verbose:
            _iter = tqdm(
                range(self.input_shape[1]), desc='Calculating permutation importance')
        else:
            _iter = range(self.input_shape[1])

        # Get baseline score
        if X_valid is None:
            pred = self.predict(X, pred_method)
            baseline_score = eval_metric(y, pred)
        else:
            pred = self.predict(X_valid, pred_method)
            baseline_score = eval_metric(y_valid, pred)
        permutation_scores = np.empty(self.input_shape[1])

        # Get permutation importances
        for icol in _iter:
            X_shuffled = copy(X)
            X_shuffled[:, icol] = np.random.permutation(X_shuffled[:, icol])
            self.train(X_shuffled, y, X_valid, y_valid,
                       cat_features, fit_params)
            if X_valid is None:
                pred = self.predict(X, pred_method)
                permutation_scores[icol] = eval_metric(y, pred)
            else:
                pred = self.predict(X_valid, pred_method)
                permutation_scores[icol] = eval_metric(y_valid, pred)
            del X_shuffled, pred; gc.collect()

        # Calculation feature score
        permutation_importances = permutation_scores - baseline_score
        self.permutation_importances = permutation_importances
        return permutation_importances

    def get_coeffcients(self):
        if self.model_type in ['LinearRegression', 'LogisticRegression',
                               'Ridge', 'Lasso']:
            return self.model.coef_
        elif self.model_type in ['SVR', 'SVC'] and self.model.get_params()['kernel'] == 'linear':
            return self.model.coef_
        else:
            return np.zeros(self.input_shape[1])

    def plot_feature_importances(self, columns=None, method='fast'):
        imps = self.get_feature_importances(method)

        if columns is None:
            columns = [f'feature_{i}' for i in range(len(imps))]

        plt.figure(figsize=(5, int(len(columns) / 3)))
        order = np.argsort(imps)
        colors = colormap.winter(np.arange(len(columns))/len(columns))
        plt.barh(np.array(columns)[order], imps[order], color=colors)
        plt.show()
        

class CrossValidator:
    '''
    Make cross validation easy again
    
    # Usage
    skf = StratifiedKFold(n_splits=5, shuffle=True, random_state=seed)
    cat_cv = CrossValidator(CatBoostClassifier(**CAT_PARAMS), skf)
    cat_cv.run(
        X, y, x_test, 
        eval_metric=AUC(), prediction='predict', 
        cat_features=CAT_IDXS,
        fit_params=CAT_FIT_PARAMS,
        verbose=0
    )
    '''
    def __init__(self, model, datasplit):
        self.basemodel = copy(model)
        self.datasplit = datasplit
        self.models = []
        self.oof = None
        self.pred = None
        self.imps = None

    def run(self, X, y, X_test=None, group=None, n_splits=None, 
            # Dataset
            cat_features=None, categorical_features=None, transform=None, 
            fit_params={}, eval_metric=None,  # Training
            # Prediction
            pred_method='predict', prediction=None, importance_method='fast', 
            calibration=False, calibration_params={'method':'isotonic', 'cv':3}, 
            # Logger
            print_time=True, round_float=6, verbose=True):

        if cat_features is None and categorical_features is not None:
            cat_features = categorical_features
        elif cat_features is not None and categorical_features is not None:
            print('cat_features and categorical_features conflicts. cat_features will be ignored.')
            cat_features = categorical_features
        if prediction is not None: # depreciated
            print('[CV] Option "prediction" is depreciated. Use "pred_method" instead.')
            pred_method = prediction
        if not isinstance(eval_metric, (list, tuple, set)):
            eval_metric = [eval_metric]

        K = self.datasplit.get_n_splits() if n_splits is None else n_splits
        self.imps = np.zeros((X.shape[1], K))
        self.scores = np.zeros((len(eval_metric), K))

        for fold_i, (train_idx, valid_idx) in enumerate(
            self.datasplit.split(X, y, group)):

            Xs = {'train': X[train_idx], 'valid': X[valid_idx], 
                  'test': X_test.copy() if X_test is not None else None}
            ys = {'train': y[train_idx], 'valid': y[valid_idx]}

            if transform is not None:
                transform(Xs, ys)

            if verbose > 0:
                print(f'\n\n-----\n {K} fold cross validation. \n Starting fold {fold_i+1}\n-----\n')
                print(f'[CV]train: {len(train_idx)} / valid: {len(valid_idx)}')

            model = Trainer(deepcopy(self.basemodel))
            model.train(
                Xs['train'], ys['train'], Xs['valid'], ys['valid'], 
                cat_features=cat_features, fit_params=fit_params,
                calibration=calibration, calibration_params=calibration_params
            )
            self.models.append(model.get_model())
            oof = model.predict(Xs['valid'], pred_method)
            if X_test is not None:
                pred = model.predict(Xs['test'], pred_method) / K 

            if verbose > 0:
                print(f'best iteration is {model.get_best_iteration()}')

            if fold_i == 0:  # Initialize oof and prediction
                if len(oof.shape) == 1:
                    self.oof = np.zeros(X.shape[0], dtype=np.float)
                    if X_test is not None:
                        self.pred = np.zeros(X_test.shape[0], dtype=np.float)
                else:
                    self.oof = np.zeros((X.shape[0], oof.shape[1]), dtype=np.float)
                    if X_test is not None:
                        self.pred = np.zeros((X_test.shape[0], pred.shape[1]), dtype=np.float)

            self.oof[valid_idx] = oof
            if X_test is not None:
                self.pred += pred
            
            self.imps[:, fold_i] = model.get_feature_importances(
                method=importance_method, 
                importance_params={
                    'X': Xs['train'], 'y': ys['train'],
                    'X_valid': Xs['valid'], 'y_valid': ys['valid'],
                    'cat_features': cat_features, 'pred_method': pred_method, 
                    'iteration': 20, 'eval_metric': eval_metric[0],
                    'verbose': verbose
                }
            )
            
            for i, _metric in enumerate(eval_metric):
                score = _metric(ys['valid'], oof)
                self.scores[i, fold_i] = score
            
            if verbose >= 0:
                log_str = f'[CV] Fold {fold_i+1}:'
                log_str += ''.join([f' m{i}={self.scores[i, fold_i]:.{round_float}f}' for i in range(len(eval_metric))])
                log_str += f' (iter {model.get_best_iteration()})'
                print(log_str)

        log_str = f'[CV] Overall:'
        log_str += ''.join(
            [f' m{i}={me:.{round_float}f}±{se:.{round_float}f}' for i, (me, se) in enumerate(zip(
                np.mean(self.scores, axis=1), 
                np.std(self.scores, axis=1)/np.sqrt(len(eval_metric))
            ))]
        )
        print(log_str)
        
    def plot_feature_importances(self, columns=None):
        if columns is None:
            columns = [f'feature_{i}' for i in range(len(self.imps))]
        plt.figure(figsize=(5, int(len(columns) / 3)))
        imps_mean = np.mean(self.imps, axis=1)
        imps_se = np.std(self.imps, axis=1) / np.sqrt(self.imps.shape[0])
        order = np.argsort(imps_mean)
        colors = colormap.winter(np.arange(len(columns))/len(columns))
        plt.barh(np.array(columns)[order],
                imps_mean[order], xerr=imps_se[order], color=colors)
        plt.show()

    def save_feature_importances(self, path, columns=None):
        if columns is None:
            columns = [f'feature_{i}' for i in range(len(self.imps))]
        plt.figure(figsize=(5, int(len(columns) / 3)))
        imps_mean = np.mean(self.imps, axis=1)
        imps_se = np.std(self.imps, axis=1) / np.sqrt(self.imps.shape[0])
        order = np.argsort(imps_mean)
        colors = colormap.winter(np.arange(len(columns))/len(columns))
        plt.barh(np.array(columns)[order],
                 imps_mean[order], xerr=imps_se[order], color=colors)
        plt.savefig(path)

    def save(self, path):
        objects = [
            self.basemodel, self.datasplit, 
            self.models, self.oof, self.pred, self.imps
        ]
        with open(path, 'wb') as f:
            pickle.dump(objects, f)
    
    def load(self, path):
        with open(path, 'rb') as f:
            objects = pickle.load(f)
        
        self.basemodel, self.datasplit, self.models, \
            self.oof, self.pred, self.imps = objects


class InfoldTargetEncoder:
    '''
    Target encoder w/o target leak
    '''

    def __init__(self, categorical_features, encoder=None):
        if encoder is None:
            if EXT_CE:
                self.encoder = ce.TargetEncoder(cols=np.arange(len(categorical_features)), 
                                                return_df=False)
            else:
                self.encoder = CatEncoder(encoding='target')
        else:
            self.encoder = encoder
        self.cat_idx = categorical_features

    def __call__(self, Xs, ys):
        self.encoder.fit(Xs['train'][:, self.cat_idx], ys['train'])
        for key in Xs.keys():
            if Xs[key] is None:
                continue
            Xs[key][:, self.cat_idx] = self.encoder.transform(Xs[key][:, self.cat_idx])


'''
Feature selection
'''

class AdversarialValidationInspector:
    '''
    Feature selection by adversarial validation
    '''
    def __init__(self, model, X, y, eval_metric=roc_auc_score):
        if isinstance(model, Trainer):
            self.trainer = deepcopy(model)
        else:
            assert model
        
        self.X = X
        self.y = y

    def run(self, train_params, verbose=False):
        # Get adversarial score
        self.trainer.train(self.X, self.y, **train_params)
        self.adv_scores = self.trainer.get_feature_importances()

    def show(self, columns=None):
        if columns is None:
            columns = [f'feature_{i}' for i in range(self.X.shape[1])]

        plt.figure(figsize=(5, int(len(columns) / 3)))
        order = np.argsort(self.adv_scores)
        colors = colormap.winter(np.arange(len(columns))/len(columns))
        plt.barh(np.array(columns)[order],
                 self.adv_scores[order], color=colors)
        plt.show()

    def best(self, n=5, columns=None):
        order = np.argsort(self.adv_scores)[::-1]
        if columns is None:  # return index
            return np.arange(len(self.adv_scores))[order[:n]]
        else:
            return np.array(columns)[order[:n]]

    def worst(self, n=5, columns=None):
        order = np.argsort(self.adv_scores)
        if columns is None:  # return index
            return np.arange(len(self.adv_scores))[order[:n]]
        else:
            return np.array(columns)[order[:n]]


'''
Model selection
'''

class StratifiedGroupKFold:
    '''
    scikit-learn like inplementation of StratifiedGroupKFold
    '''

    def __init__(self, n_splits, random_state=None):

        self.n_splits = n_splits
        self.random_state = random_state

    def split(self, X, y, groups):

        labels_num = np.max(y) + 1
        y_counts_per_group = defaultdict(lambda: np.zeros(labels_num))
        y_distr = Counter()
        for label, g in zip(y, groups):
            y_counts_per_group[g][label] += 1
            y_distr[label] += 1

        y_counts_per_fold = defaultdict(lambda: np.zeros(labels_num))
        groups_per_fold = defaultdict(set)

        def eval_y_counts_per_fold(y_counts, fold):
            y_counts_per_fold[fold] += y_counts
            std_per_label = []
            for label in range(labels_num):
                label_std = np.std(
                    [y_counts_per_fold[i][label] / y_distr[label] for i in range(self.n_splits)])
                std_per_label.append(label_std)
            y_counts_per_fold[fold] -= y_counts
            return np.mean(std_per_label)

        groups_and_y_counts = list(y_counts_per_group.items())
        random.Random(self.random_state).shuffle(groups_and_y_counts)

        for g, y_counts in sorted(groups_and_y_counts, key=lambda x: -np.std(x[1])):
            best_fold = None
            min_eval = None
            for i in range(self.n_splits):
                fold_eval = eval_y_counts_per_fold(y_counts, i)
                if min_eval is None or fold_eval < min_eval:
                    min_eval = fold_eval
                    best_fold = i
            y_counts_per_fold[best_fold] += y_counts
            groups_per_fold[best_fold].add(g)

        all_groups = set(groups)
        for i in range(self.n_splits):
            train_groups = all_groups - groups_per_fold[i]
            test_groups = groups_per_fold[i]

            train_indices = [i for i, g in enumerate(
                groups) if g in train_groups]
            test_indices = [i for i, g in enumerate(
                groups) if g in test_groups]

            yield train_indices, test_indices

    def get_n_splits(self):
        return self.n_splits
