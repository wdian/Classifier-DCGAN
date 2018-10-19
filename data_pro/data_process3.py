#!/usr/bin/env python
# -- coding = 'utf-8' --
# Author:wdian
# Python Version:3.6
# OS:Windows 10

'''将csv中不存在图像样本的信息删除'''




import pandas as pd
import numpy as np
import os

root_dir = "E:/Project/X_Ray/image_total"
df = pd.DataFrame(pd.read_csv('document/data_choose.csv'))
print(df.columns.values)

data=df[df['Image Index'].isin(os.listdir(root_dir))]
print(data)

data.to_csv("document/data_single.csv")
data.to_excel("document/data_single.xlsx")