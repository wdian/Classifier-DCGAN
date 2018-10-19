#!/usr/bin/env python
# -- coding = 'utf-8' --
# Author:wdian
# Python Version:3.6
# OS:Windows 10

'''将原始csv中不存在图像样本的信息删除'''
import pandas as pd
import numpy as np
import os

root_dir = "E:/Project/X光/image_total"
col_n =['Image Index', 'Finding Labels']


df = pd.DataFrame(pd.read_csv("data/Data_Entry_2017.csv"),columns=col_n)
print(df.columns.values)


name = df.iloc[:, 0]
label = df.iloc[:, 1]


"""
num = 0
for file in os.listdir(root_dir):
    for i in name:
        if i in file:
            pass
        else:
            num+=1
"""


data=df[df['Image Index'].isin(os.listdir(root_dir))]

print(data.shape)
print(data.head())

data.to_csv("data/data_choose.csv")
data.to_excel("data/data_choose.xlsx")

