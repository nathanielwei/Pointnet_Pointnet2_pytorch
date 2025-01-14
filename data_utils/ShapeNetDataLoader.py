# *_*coding:utf-8 *_*
import os
import json
import warnings
import numpy as np
from torch.utils.data import Dataset
warnings.filterwarnings('ignore')

def pc_normalize(pc):
    centroid = np.mean(pc, axis=0) # Nate: Take x_mean, y_mean, z_mean as centriod
    pc = pc - centroid # Nate: re-center 
    m = np.max(np.sqrt(np.sum(pc ** 2, axis=1))) # Nate: compute np.sqrt(x^2+y^2+z^2), find the largest one
    pc = pc / m # Nate: make every point clould in a ball with radius 1
    return pc

class PartNormalDataset(Dataset):
    def __init__(self,root = './data/shapenetcore_partanno_segmentation_benchmark_v0_normal', npoints=2500, split='train', class_choice=None, normal_channel=False):
        self.npoints = npoints # Nate: in train.py, npoints = 2048; if use --normal in bash file, then normal_channel = True
        self.root = root
        self.catfile = os.path.join(self.root, 'synsetoffset2category.txt')
        self.cat = {}
        self.normal_channel = normal_channel


        with open(self.catfile, 'r') as f:
            for line in f:
                ls = line.strip().split()
                self.cat[ls[0]] = ls[1]
        self.cat = {k: v for k, v in self.cat.items()}
        self.classes_original = dict(zip(self.cat, range(len(self.cat))))

        if not class_choice is  None:
            self.cat = {k:v for k,v in self.cat.items() if k in class_choice}
        # print(self.cat)

        self.meta = {}
        with open(os.path.join(self.root, 'train_test_split', 'shuffled_train_file_list.json'), 'r') as f:
            train_ids = set([str(d.split('/')[2]) for d in json.load(f)])
        with open(os.path.join(self.root, 'train_test_split', 'shuffled_val_file_list.json'), 'r') as f:
            val_ids = set([str(d.split('/')[2]) for d in json.load(f)])
        with open(os.path.join(self.root, 'train_test_split', 'shuffled_test_file_list.json'), 'r') as f:
            test_ids = set([str(d.split('/')[2]) for d in json.load(f)])
        for item in self.cat:
            # print('category', item)
            self.meta[item] = []
            dir_point = os.path.join(self.root, self.cat[item])
            fns = sorted(os.listdir(dir_point))
            # print(fns[0][0:-4])
            if split == 'trainval':
                fns = [fn for fn in fns if ((fn[0:-4] in train_ids) or (fn[0:-4] in val_ids))]
            elif split == 'train':
                fns = [fn for fn in fns if fn[0:-4] in train_ids]
            elif split == 'val':
                fns = [fn for fn in fns if fn[0:-4] in val_ids]
            elif split == 'test':
                fns = [fn for fn in fns if fn[0:-4] in test_ids]
            else:
                print('Unknown split: %s. Exiting..' % (split))
                exit(-1)

            # print(os.path.basename(fns))
            for fn in fns:
                token = (os.path.splitext(os.path.basename(fn))[0])
                self.meta[item].append(os.path.join(dir_point, token + '.txt')) 
                # Nate: meta save all pc files for each category, e.g. meta['Chair'] is a list of paths for txt files
        self.datapath = []
        for item in self.cat: # Nate: iter each category 
            for fn in self.meta[item]: # Nate: append all paths for each category
                self.datapath.append((item, fn)) # Nate: e.g. 'Chair', [txt file path] 

        self.classes = {}
        for i in self.cat.keys(): # Nate:  'Airplane', 'Chair' ...
            self.classes[i] = self.classes_original[i] # Nate: classes_original is dict. e.g. 'Airplane': 0, ...

        # Mapping from category ('Chair') to a list of int [10,11,12,13] as segmentation labels
        self.seg_classes = {'Earphone': [16, 17, 18], 'Motorbike': [30, 31, 32, 33, 34, 35], 'Rocket': [41, 42, 43],
                            'Car': [8, 9, 10, 11], 'Laptop': [28, 29], 'Cap': [6, 7], 'Skateboard': [44, 45, 46],
                            'Mug': [36, 37], 'Guitar': [19, 20, 21], 'Bag': [4, 5], 'Lamp': [24, 25, 26, 27],
                            'Table': [47, 48, 49], 'Airplane': [0, 1, 2, 3], 'Pistol': [38, 39, 40],
                            'Chair': [12, 13, 14, 15], 'Knife': [22, 23]}

        # for cat in sorted(self.seg_classes.keys()):
        #     print(cat, self.seg_classes[cat])

        self.cache = {}  # from index to (point_set, cls, seg) tuple
        self.cache_size = 20000


    def __getitem__(self, index):
        if index in self.cache:
            point_set, cls, seg = self.cache[index] # Nate: cache is a dict: e.g. 0, np.array
        else:
            fn = self.datapath[index]
            cat = self.datapath[index][0]
            cls = self.classes[cat]
            cls = np.array([cls]).astype(np.int32)
            data = np.loadtxt(fn[1]).astype(np.float32) # Nate each col: x,y,z,r,g,b,seg-class
            if not self.normal_channel:
                point_set = data[:, 0:3] # Nate: use XYZ only
            else:
                point_set = data[:, 0:6] # Nate: use XYZ and RGB, then [x,y,z,r,g,b] e.g. when training uses --normal
            seg = data[:, -1].astype(np.int32)
            if len(self.cache) < self.cache_size:
                self.cache[index] = (point_set, cls, seg) # Nate: their shapes e.g. (2747, 3), (1,) (2747,), respectively
        point_set[:, 0:3] = pc_normalize(point_set[:, 0:3])

        choice = np.random.choice(len(seg), self.npoints, replace=True) # Nate: generate [npoints] each value between 0 and len(seg)-1 
        # resample
        point_set = point_set[choice, :] # Nate e.g. (2500, 3) the selected points may not be unique, in train.py: (2048, 6) or (2048, 3)
        seg = seg[choice] # Nate e.g. (2500,)

        return point_set, cls, seg

    def __len__(self):
        return len(self.datapath)



