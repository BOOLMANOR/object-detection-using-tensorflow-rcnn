import numpy as np
import tensorflow as tf

import Configuration as cfg

class AlexNet:
    def __init__(self, model, mean, trainable):
        self.model = model
        self.mean = mean
        self.var_dict = {}
        self.trainable = trainable

    def build(self, img_holder, label_holder=None):
        b, g, r = tf.split(axis=3, num_or_size_splits=3, value=img_holder)
        bgr = tf.concat(axis=3, values=[b - self.mean[0], g - self.mean[1], r - self.mean[2]])

        self.conv1 = self.conv_layer(bgr, 3, 96, 11, 4, 'VALID', 'conv1')
        self.norm1 = self.lr_norm(self.conv1, 'norm1')
        self.pool1 = self.max_pool(self.norm1, 3, 2, 'VALID', 'pool1')

        self.conv2 = self.conv_layer(self.pool1, 96, 256, 5, 1, 'SAME', 'conv2')
        self.norm2 = self.lr_norm(self.conv2, 'norm2')
        self.pool2 = self.max_pool(self.norm2, 3, 2, 'VALID', 'pool2')

        self.conv3 = self.conv_layer(self.pool2, 256, 384, 3, 1, 'SAME', 'conv3')
        self.conv4 = self.conv_layer(self.conv3, 384, 384, 3, 1, 'SAME', 'conv4')
        self.conv5 = self.conv_layer(self.conv4, 384, 256, 3, 1, 'SAME', 'conv5')
        self.pool5 = self.max_pool(self.conv5, 3, 2, 'VALID', 'pool5')

        self.fc6 = self.fc_layer(self.pool5, 9216, 4096, 'fc6')
        self.relu6 = tf.nn.relu(self.fc6)

        if self.trainable:
            self.relu6 = tf.nn.dropout(self.relu6, 0.5)

        self.fc7 = self.fc_layer(self.relu6, 4096, 4096, 'fc7')
        self.relu7 = tf.nn.relu(self.fc7)
        self.tanh7 = tf.nn.tanh(self.fc7)

        if self.trainable:
            self.relu7 = tf.nn.dropout(self.relu7, 0.5)

        self.fc8 = self.fc_layer(self.relu7, 4096, cfg.object_class_num, 'fc8')

        self.prob = tf.nn.softmax(self.fc8, name='prob')

        if self.trainable:
            self.loss = tf.nn.softmax_cross_entropy_with_logits(logits=self.fc8, labels=label_holder)
            self.loss_mean = tf.reduce_mean(self.loss)
            self.optimizer = tf.train.AdamOptimizer(learning_rate=0.0025).minimize(self.loss_mean)

            self.correct_prediction = tf.equal(tf.argmax(self.fc8, 1), tf.argmax(label_holder, 1))
            self.accuracy_mean = tf.reduce_mean(tf.cast(self.correct_prediction, tf.float32))

        self.model = None

    def build_finetune(self, label_holder=None):
        self.finetune_fc8 = self.fc_layer(self.relu7, 4096, cfg.object_class_num + 1, 'finetune_fc8')

        self.finetune_prob = tf.nn.softmax(self.finetune_fc8, name='finetune_prob')

        if self.trainable:
            self.finetune_loss = tf.nn.softmax_cross_entropy_with_logits(logits=self.finetune_fc8, labels=label_holder)
            self.finetune_loss_mean = tf.reduce_mean(self.finetune_loss)
            self.finetune_optimizer = tf.train.GradientDescentOptimizer(learning_rate=0.0001).minimize(self.finetune_loss_mean)

            self.finetune_correct_prediction = tf.equal(tf.argmax(self.finetune_fc8, 1), tf.argmax(label_holder, 1))
            self.finetune_accuracy_mean = tf.reduce_mean(tf.cast(self.finetune_correct_prediction, tf.float32))

    def get_var(self, initial_value, name, idx, var_name):
        if self.model is not None and name in self.model:
            value = self.model[name][idx]
        else:
            value = initial_value

        var = tf.Variable(value, name=var_name)

        self.var_dict[(name, idx)] = var

        return var

    def get_conv_var(self, filter_size, in_channels, out_channels, name):
        initial_value = tf.truncated_normal([filter_size, filter_size, in_channels, out_channels], 0.0, 0.001)
        filters = self.get_var(initial_value, name, 0, name + '_filters')

        initial_value = tf.truncated_normal([out_channels], 0.0, 0.001)
        biases = self.get_var(initial_value, name, 1, name + '_biases')

        return filters, biases

    def get_fc_var(self, in_size, out_size, name):
        initial_value = tf.truncated_normal([in_size, out_size], 0.0, 0.001)
        weights = self.get_var(initial_value, name, 0, name + '_weights')

        initial_value = tf.truncated_normal([out_size], 0.0, 0.001)
        biases = self.get_var(initial_value, name, 1, name + '_biases')

        return weights, biases

    def conv_layer(self, bottom, in_channels, out_channels, filter_size, stride_size, padding_type, name):
        with tf.variable_scope(name):
            filt, conv_biases = self.get_conv_var(filter_size, in_channels, out_channels, name)

            conv = tf.nn.conv2d(bottom, filter=filt, strides=[1, stride_size, stride_size, 1], padding=padding_type)
            bias = tf.nn.bias_add(conv, conv_biases)
            relu = tf.nn.relu(bias)

            return relu

    def fc_layer(self, bottom, in_size, out_size, name):
        with tf.variable_scope(name):
            weights, biases = self.get_fc_var(in_size, out_size, name)

            x = tf.reshape(bottom, [-1, in_size])
            fc = tf.nn.bias_add(tf.matmul(x, weights), biases)

            return fc

    def lr_norm(self, bottom, name):
        return tf.nn.local_response_normalization(bottom, depth_radius=2, alpha=1e-4, beta=0.75, name=name)

    def avg_pool(self, bottom, name):
        return tf.nn.avg_pool(bottom, ksize=[1, 2, 2, 1], strides=[1, 2, 2, 1], padding='SAME', name=name)

    def max_pool(self, bottom, kernel_size, stride_size, padding_type, name):
        return tf.nn.max_pool(bottom, ksize=[1, kernel_size, kernel_size, 1], strides=[1, stride_size, stride_size, 1], padding=padding_type, name=name)

    def get_var_count(self):
        count = 0
        for var in list(self.var_dict.values()):
            count += np.multiply(var.get_shape().as_list())
        return count
