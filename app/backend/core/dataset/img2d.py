from input import *
import numpy as np
import skimage.io as skimgio
import PIL.Image
import imghdr
from img2d_utils import ImageTransformer2D

try:
    from cStringIO import StringIO
except ImportError:
    from StringIO import StringIO


class Img2DColumn(ComplexColumn):
    def __init__(self, name=None, pre_transforms=[], post_transforms=[], is_raw_img=False, reader=None, aggregators=[]):
        super(Img2DColumn, self).__init__(name=name,
                                          type=Column.Type.IMG_2D,
                                          ser_de=Img2DSerDe(is_raw_img),
                                          reader=reader,
                                          pre_transforms=pre_transforms,
                                          post_transforms=post_transforms,
                                          aggregators=aggregators)
        if reader is None:
            self._reader = Img2DReader(self)

    @property
    def schema(self):
        schema = super(Img2DColumn, self).schema
        pre_transforms = []
        for transform in self.pre_transforms:
            pre_transforms.append(transform.schema)
        schema['pre_transforms'] = pre_transforms
        post_transforms = []
        for transform in self.post_transforms:
            post_transforms.append(transform.schema)
        schema['post_transforms'] = post_transforms
        return schema

    class Builder(object):
        def __init__(self, img2d_column_config):
            self._img2d_column_config = img2d_column_config

        def build(self):
            pre_transforms = []
            post_transforms = []
            for pre_transform in self._img2d_column_config["pre_transforms"]:
                pre_transforms.append(self._build_transform(pre_transform))

            for post_transform in self._img2d_column_config["post_transforms"]:
                post_transforms.append(self._build_transform(post_transform))

            indexes = None
            if 'index' in self._img2d_column_config:
                indexes = self._img2d_column_config['index']

            img2d = Img2DColumn(str(self._img2d_column_config['name']), pre_transforms, post_transforms)
            img2d.columns_indexes = indexes
            return img2d

        @staticmethod
        def _build_transform(transform):
            type = transform["type"]
            params = transform["params"]
            if type == ImgCropTransform.type():
                return ImgCropTransform(params)
            if type == ImgResizeTransform.type():
                return ImgResizeTransform(params)
            if type == ImgNormalizationTransform.type():
                return ImgNormalizationTransform.Builder(params).build()
            raise TypeError("Unsupported column transform type: %s" % transform)


class ImgCropTransform(ColumnTransform):
    def __init__(self, shape):
        super(ImgCropTransform, self).__init__()
        self.out_shape = shape

    @staticmethod
    def type():
        return "imgCrop"

    def apply(self, data):
        return ImageTransformer2D.transformCropImage(data, self.out_shape)

    @property
    def schema(self):
        return {}

    class Builder:
        def __init__(self, params):
            self._params = params

        def build(self):
            height = int(self._params['height'])
            width = int(self._params['width'])
            return ImgCropTransform((height, width))


class ImgResizeTransform(ColumnTransform):
    def __init__(self, params):
        super(ImgResizeTransform, self).__init__()

    @staticmethod
    def type():
        return "imgResize"

    def apply(self, data):
        return data

    @staticmethod
    def config():
        return {'type': 'input'}

    @property
    @abc.abstractmethod
    def schema(self):
        return {}


class ImgNormalizationTransform(ColumnTransform):
    def __init__(self, is_global, mean=None, std=None):
        super(ImgNormalizationTransform, self).__init__()
        self.is_global = is_global
        if self.is_global:
            self.mean = mean
            self.std = std
        else:
            self.mean = 0.
            self.std = 1.

    class Builder:
        def __init__(self, params):
            self._params = params

        def build(self):
            is_global = True if self._params['is_global'] == "True" else False
            mean = None
            std = None
            if is_global:
                mean = float(self._params['mean'])
                std = float(self._params['std'])
            return ImgNormalizationTransform(is_global, mean, std)

    @staticmethod
    def type():
        return "imgNormalization"

    def apply(self, data):
        if self.is_global:
            return (data - self.mean) / data.std
        else:
            tmean = data.mean()
            tstd  = data.std()
            return (data - tmean)/tstd

    @property
    @abc.abstractmethod
    def schema(self):
        return {}


class Img2DReader(ColumnReader):
    def __init__(self, column):
        super(Img2DReader, self).__init__(column)

    def read(self, csv_row):
        path = str(csv_row[self._column.columns_indexes[0]])
        img_data = skimgio.imread(path)
        img_fmt = imghdr.what(path)
        return img_data, img_fmt


class Img2DSerDe(ColumnSerDe):
    def __init__(self, is_raw_img):
        self._is_raw_img = is_raw_img

    def serialize(self, img):
        img_data = img[0]
        img_fmt = img[1]
        img_ser = {}
        if self._is_raw_img:
            img_ser['rows'] = img_data.shape[0]
            img_ser['cols'] = img_data.shape[1]
            img_ser['ch_num'] = 1
            if len(img_data.shape) > 2:
                img_ser['ch_num'] = img_data.shape[2]
            img_ser['data'] = img_data.tostring()
        else:
            img_array = PIL.Image.fromarray(img_data.astype(np.uint8))
            img_buffer = StringIO()
            img_array.save(img_buffer, format=img_fmt)
            img_ser['data'] = img_buffer.getvalue()

        return img_ser

    def deserialize(self, img):
        if 'cols' in img:
            rows = img['rows']
            cols = img['cols']
            ch_num = img['ch_num']
            img = np.frombuffer(img['data'], dtype=np.uint8)
            if ch_num==1:
                img = img.reshape((rows, cols))
            else:
                img = img.reshape((rows, cols, ch_num))
        else:
            img = skimgio.imread(StringIO(img['data']))

        return img
