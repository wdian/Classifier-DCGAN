#!/usr/bin/env python
# -- coding = 'utf-8' --
# Author:wdian
# Python Version:3.6
# OS:Windows 10
'''删除多标签图像'''

import pandas as pd
import sys
import os

df = pd.read_csv('document/data_choose.csv')
img_dir = 'E:\Project\X_Ray\image_total'

name = df.iloc[:, 1]
label = df.iloc[:, 2]

path = 'E:\Project\X_Ray\image_total'
print("path:", path)


label_sp= label[0].split('|')                        #文本分割
# print(label_sp)

for i in range(36509):
    if '|' in label[i]:
        if name[i] in os.listdir(path):
            os.remove(os.path.join(path, name[i]))


# for i in range(36510):
#     olddir =os.path.join(path, name[i])
#     newdir =os.path.join(path, label[i]+"_%04d"%(i)+'.png')
#     os.rename(olddir, newdir)







