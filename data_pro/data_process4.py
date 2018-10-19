#!/usr/bin/env python
# -- coding = 'utf-8' --
# Author:wdian
# Python Version:3.6
# OS:Windows 10

'''文件重命名'''

import pandas as pd
import sys
import os

df = pd.read_csv('document/data_single.csv')
path = 'E:\Project\X_Ray\image_total'

name = df.iloc[:, 0]
label = df.iloc[:, 1]


print("path:", path)


# label_sp= label[0].split('|')                        #文本分割
# # print(label_sp)


for i in range(30370):
    olddir =os.path.join(path, name[i])
    newdir =os.path.join(path, label[i]+"_%04d"%(i)+'.png')
    os.rename(olddir, newdir)
