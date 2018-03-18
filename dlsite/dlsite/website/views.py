# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.urls import resolve
from django.conf import settings
from django.shortcuts import render
from rest_framework.views import APIView
from rest_framework.response import Response

from random import sample
from collections import defaultdict
from os import listdir, curdir, path
from .models import Image, Keyword, Statistics, ClfModel, Label, ClusterModel, ImageCluster

import numpy as np
import pandas as pd

from recommend import get_relevant_imgs, get_img_map
import math


ABS_PATH = path.dirname(path.abspath(__file__))
FEEDBACK_IMG_SEP = "/"
FEEDBACK_FILE = ABS_PATH + settings.STATIC_URL + "feedback.csv"
FEEDBACK_COLS = ["query", "step", "image", "status"]
print("FEEDBACK_FILE:", FEEDBACK_FILE)

PATH_TO_IMAGES_FRONTEND = "mlimages/"
PATH_TO_IMAGES = ABS_PATH.split('dlsite')[0] + 'frontend/public/' + PATH_TO_IMAGES_FRONTEND

print("PATH_TO_IMAGES", PATH_TO_IMAGES)

indices_euclidean_path = ABS_PATH + settings.STATIC_URL + "indices_euclidean.csv"
INDICIES = np.genfromtxt(indices_euclidean_path, delimiter=',', dtype=str)
# INDICIES = INDICIES[:1000]

distances_euclidean_path = ABS_PATH + settings.STATIC_URL + "distances_euclidean.csv"
DISTANCES = np.genfromtxt(distances_euclidean_path, delimiter=',')
# DISTANCES = DISTANCES[:1000]

IMG_MAP = None

inception_layer_path = ABS_PATH + settings.STATIC_URL + "inception_output_layer2"
print("READ inception_layer_path")
df_in = pd.read_pickle(inception_layer_path)
df_in.columns = ['img', 'output_layer', 'scores']
print("DROP column - output_layer")
df_in.drop('output_layer', axis=1, inplace=True)
print(df_in.head())
known_words = defaultdict(list)


def prepare_known_words():
    global df_in, known_words
    print("create dict of known words")
    rows = df_in.shape[0]
    for i in range(rows):
        row = df_in.iloc[i]
        img_title = row['img']
        descriptions_list = row['scores'].items()
        for d, score in descriptions_list:
            for word in d.split(' '):
                known_words[word].append((img_title, score))

    print('==================== known_words', len(known_words))
    print("del df_in")
    del df_in
    print("done")
prepare_known_words()


def index(request):
    # images_list = Image.objects.all()
    # context = {'images_list': images_list, 'count': len(images_list)}
    # return render(request, 'index.html', context)
    return render(request, 'index.html', {})


def load_images_list():
    images_titles = [f for f in listdir(PATH_TO_IMAGES) if f.endswith(".jpg")]
    images_titles = sorted(images_titles, reverse=False)
    return images_titles


def get_random_images(count=20):
    """Get image titles from DB

    :return: list of strings
    """
    # TODO: take random images from ClusterImage ==============================================

    images = Image.objects.all()
    subset = sample(images, count)
    print("get random", count, "images. result ->", len(subset))
    return [PATH_TO_IMAGES_FRONTEND + i.title for i in subset]


def keyword_exists(k):
    """Check if keyword have been searched before

    :param k: string, search keyword
    :return: boolean
    """
    q = Keyword.objects.filter(keyword__exact=k)
    if not q:
        return False
    return True


def format_response(query, step, images):
    return {
        "step": step,
        "query": query,
        "images": images,
        "ok": True
    }


def send_random(q):
    """Return dict with random images

    :param q: query string
    :return: dict
    """
    step = 0
    images = get_random_images()

    return format_response(q, step, images)


def send_based_on_feedback(q, _df_feedback):
    """Return dict with images based on saved feedback

    :param q: query string
    :param _df_feedback: feedback df
    :return: dict
    """

    images = get_relevant_images_based_on_feedback(q, _df_feedback)
    if images is None:
        images = get_random_images()
    return format_response(q, 0, images)


def save_feedback(d, _df_feedback):
    print("============================== run save_feedback")
    query = d.get("query")
    step = d.get("step")
    selected_img = d.get("selectedImages")
    not_selected_img = d.get("nonSelectedImages")
    print(query)
    print(step)
    print(selected_img)
    print(not_selected_img)

    res = []
    for img in selected_img:
        img_title = img.split(FEEDBACK_IMG_SEP)[-1]
        res.append([query, step, img_title, "1"])

    for img in not_selected_img:
        img_title = img.split(FEEDBACK_IMG_SEP)[-1]
        res.append([query, step, img_title, "0"])

    print("create df_tmp")
    df_tmp = pd.DataFrame(res)
    df_tmp.columns = FEEDBACK_COLS
    print("df_tmp head")
    print(df_tmp.head())
    print("append")
    _df_feedback = _df_feedback.append(df_tmp, ignore_index=True)
    print("save")
    _df_feedback.to_csv(FEEDBACK_FILE, index=False)

    return True


def read_feedback():
    if path.isfile(FEEDBACK_FILE):
        return pd.read_csv(FEEDBACK_FILE)

    df = pd.DataFrame({}, columns=FEEDBACK_COLS)
    df.to_csv(FEEDBACK_FILE, index=False)
    return df
df_feedback = read_feedback()
print(df_feedback.head())


def get_similar_images(images, k=20):
    global IMG_MAP

    print("run get_similar_images")
    if IMG_MAP is None:
        IMG_MAP = get_img_map(load_images_list())

    print("IMG_MAP", len(IMG_MAP))
    print(IMG_MAP.items()[:10])
    print("INDICIES", len(INDICIES))
    print(INDICIES)
    print("DISTANCES", len(DISTANCES))
    print(DISTANCES)
    print("k")
    print(k)
    print("PATH_TO_IMAGES")
    print(PATH_TO_IMAGES)
    print("run get_relevant_images_rank")
    images_list = get_relevant_imgs(images, IMG_MAP, INDICIES, DISTANCES,
                                    k, form="list", rank=True, img_dir=PATH_TO_IMAGES)
    # images_list = get_relevant_images_rank(selected_img, IMG_MAP, INDICIES, DISTANCES,
    #                                        k, operation="union", img_dir=PATH_TO_IMAGES)
    print("return", len(images_list))
    return images_list


def get_similar(d, k=20):
    print("get selected_img")
    selected_img = [x.split(FEEDBACK_IMG_SEP)[-1] for x in d.get("selectedImages")]
    print(selected_img)

    return get_similar_images(selected_img, k)


def ci_lower_bound(positive, total, confidence = 0.95):
    """

    :param positive: number of positive votes
    :param total: total number of votes
    :param confidence: confidence interval
    :return:
    """
    #http://www.evanmiller.org/how-not-to-sort-by-average-rating.html

    if total == 0 or positive > total:
        return 0

    z = 1.96#Statistics2.pnormaldist(1-(1-confidence)/2)
    phat = 1.0*positive/total
    return (phat + z*z/(2*total) - z * math.sqrt((phat*(1-phat)+z*z/(4*total))/total))/(1+z*z/total)


def get_relevant_images_based_on_feedback(q, _df_feedback, count=20, upper_threshold=0.5, threshold_steps=3, lower_threshold=0.125):
    filtered = _df_feedback.loc[_df_feedback['query'] == q]
    unique_images = filtered['image'].unique().tolist()
    ratio_list = []
    for image in unique_images:
        total_times_shown = len(filtered.loc[filtered['image'] == image])
        times_selected = len(filtered.loc[(filtered['image'] == image) & (filtered['status'] == 1)])
        ratio = ci_lower_bound(times_selected, total_times_shown)
        ratio_list.append(ratio)
    ratio_df = pd.DataFrame({'image': unique_images, 'ratio': ratio_list})

    """threshold_ratio_df = ratio_df.loc[ratio_df['ratio'] > 0.5]
    threshold_ratio_df.sort_values(by='ratio', ascending=False, inplace=True)
    length = min(len(threshold_ratio_df), count)
    if length == 0:
        threshold_ratio_df = ratio_df.loc[ratio_df['ratio'] > 0.25]
        threshold_ratio_df.sort_values(by='ratio', ascending=False, inplace=True)
        length = min(len(threshold_ratio_df), count/2)
        if length == 0:
            threshold_ratio_df = ratio_df.loc[ratio_df['ratio'] > 0.125]
            threshold_ratio_df.sort_values(by='ratio', ascending=False, inplace=True)
            length = min(len(threshold_ratio_df), count / 4)
            if length == 0:
                # TODO: count those pics that were not selected to fetch images far from them
                return None
    """

    threshold_decrement = (upper_threshold - lower_threshold)/threshold_steps
    current_threshold = upper_threshold
    threshold_ratio_df = pd.DataFrame({}, columns=['image', 'ratio'])
    length = 0
    i = 1
    while current_threshold >= lower_threshold and length < count:
        ddf = ratio_df.loc[ratio_df['ratio'] >= current_threshold]
        ddf.sort_values(by='ratio', ascending=False, inplace=True)
        ddf_len = len(ddf)
        if ddf_len > 0:
            threshold_ratio_df = pd.concat([threshold_ratio_df, ddf])
            length += min(ddf_len, count/i)
            ratio_df = ratio_df.ix[ratio_df['ratio'] < current_threshold]
        i += 1
        current_threshold -= threshold_decrement

    length = min(20, length)
    if length == 0:
        # TODO: count those pics that were not selected to fetch images far from them
        return None

    images = threshold_ratio_df.head(length)['image']

    needed = count - length
    similar = get_similar_images(images, count)
    similar = map(lambda x: PATH_TO_IMAGES_FRONTEND + x.split('/')[-1], similar)
    ret_val = []
    for i in images:
        ret_val.append(PATH_TO_IMAGES_FRONTEND + i)

    filtered_similar = [x for x in similar if x not in ret_val][:needed]
    ret_val.extend(filtered_similar)
    return ret_val


class SearchView(APIView):

    def get(self, request):
        url_name = resolve(self.request.path).url_name
        print("URL name", url_name)

        if url_name == 'search':
            print("GET", request.GET)
            query = request.GET.get('query')
            if not query or len(query) == 0:
                return Response()

            query = query.lower().strip()
            print("Search for", query)

            if keyword_exists(query):
                # TODO: return normal results
                print("Keyword exists")

                return Response(send_based_on_feedback(query, df_feedback))

            else:
                print("Send random")
                print("SHOW known_words")
                print(known_words.keys()[:10])

                Keyword(keyword=query).save()
                return Response(send_random(query))

        elif url_name == 'update_images':
            print("get all images available for frontend")
            images_list = load_images_list()
            print("count images", len(images_list))
            print("first 10", images_list[:10])

            images_list = [img for img in images_list if img.endswith(".jpg")]
            bulk_list = [Image(title=img) for img in images_list]
            Image.objects.bulk_create(bulk_list)

            # for idx, img in enumerate(images_list):
            #     if idx % 100 == 0:
            #         print("======", idx)
            #     if img.endswith(".jpg"):
            #         Image(title=img).save()

            return Response({"status": "images stored",
                             "length": len(images_list)})

        elif url_name == 'remove_images_from_db':
            print("remove all images from DB")
            Image.objects.all().delete()
            print("done")
            print("retrieve all images - should be empty")
            imgs = Image.objects.all()
            print(len(imgs))
            print("done")

            return Response({"status": "images deleted"})

        else:
            pass

        return Response()

    def post(self, request):
        url_name = resolve(self.request.path).url_name
        print("URL name", url_name)

        if url_name == 'feedback':
            print("POST", request.POST)

            data = request.data
            print("Data", data)

            save_feedback(data, df_feedback)

            if not data.get("selectedImages"):
                print("No images")
                return Response(send_random(data.get("query")))

            similar_images = get_similar(data)
            similar_images = map(lambda x: PATH_TO_IMAGES_FRONTEND + x.split('/')[-1], similar_images)

            query = data.get("query")
            step = data.get("step")
            return Response(format_response(query, step + 1, similar_images))

        else:
            print("POST something else")

            data = request.data
            print("Data", data)

        return Response({"error": "post error"})
