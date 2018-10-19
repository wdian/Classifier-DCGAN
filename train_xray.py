#!/usr/bin/env python
# -- coding = 'utf-8' --
# Author:wdian
# Python Version:3.6
# OS:Windows 10

import time
import pickle

import numpy as np
import tensorflow as tf

from xray_gan import discriminator, generator
import sys
import os

# os.environ['TF_CPP_MIN_LOG_LEVEL'] = '3'

flags = tf.app.flags
flags.DEFINE_integer('gpu', 0, 'gpu [0]')
flags.DEFINE_integer('batch_size', 100, "batch size [100]")
flags.DEFINE_string('train_dir', 'data/dataset_onehot/train_set.dat', 'data directory')
flags.DEFINE_string('test_dir', 'data/dataset_onehot/test_set.dat', 'data directory')

flags.DEFINE_string('logdir', './bin/log', 'log directory')

flags.DEFINE_integer('seed', 10, 'seed numpy')
flags.DEFINE_integer('labeled', 50, 'labeled data per class [400]')

flags.DEFINE_float('learning_rate', 0.0003, 'learning_rate[0.0003]')
flags.DEFINE_float('unl_weight', 1.0, 'unlabeled weight [1.]')
flags.DEFINE_float('lbl_weight', 1.0, 'unlabeled weight [1.]')
flags.DEFINE_float('ma_decay', 0.9999, 'exponential moving average for inference [0.9999]')    #  滑动平均
flags.DEFINE_integer('decay_start', 1000, 'start learning rate decay [1200]')
flags.DEFINE_integer('epoch', 100, 'epochs [1400]')
flags.DEFINE_boolean('validation', False, 'validation [False]')

flags.DEFINE_integer('freq_print', 10000, 'frequency image print tensorboard [10000]')
flags.DEFINE_integer('step_print', 1, 'frequency scalar print tensorboard [50]')
flags.DEFINE_integer('freq_test', 1, 'frequency test [500]')
flags.DEFINE_integer('freq_save', 10, 'frequency saver epoch[50]')
FLAGS = flags.FLAGS

# 信息熵
def entropy_1(x):
    y=tf.nn.softmax(x)
    s1 = -y*tf.log(y)
    s2 = tf.reduce_sum(s1,axis=1)
    s3 = tf.reduce_mean(s2)
    return s3
#===============================================================================================
def get_getter(ema):
    def ema_getter(getter, name, *args, **kwargs):
        var = getter(name, *args, **kwargs)
        ema_var = ema.average(var)
        return ema_var if ema_var else var
    return ema_getter


def display_progression_epoch(j, id_max):
    batch_progression = int((j / id_max) * 100)
    sys.stdout.write(str(batch_progression) + ' % epoch' + chr(13))
    _ = sys.stdout.flush


def linear_decay(decay_start, decay_end, epoch):
    return min(-1 / (decay_end - decay_start) * epoch + 1 + decay_start / (decay_end - decay_start),1)

# 打印超参数
def main(_):
    print("\nParameters:")
    # FLAGS._parse_flags()
    for attr,value in FLAGS.flag_values_dict().items():
    # for attr, value in FLAGS.__flags.items():
        print("{}={}".format(attr, value))
    print("")

    os.environ["CUDA_VISIBLE_DEVICES"] = str(FLAGS.gpu)

    if not os.path.exists(FLAGS.logdir):
        os.makedirs(FLAGS.logdir)

    # Random seed
    rng = np.random.RandomState(FLAGS.seed)  # seed labels
    rng_data = np.random.RandomState(rng.randint(0, 2**10))  # seed shuffling

    # load train data
    f1 = open(FLAGS.train_dir, 'rb')
    dic = pickle.load(f1)
    trainx = dic['data']
    trainy = dic['label']
    trainy = np.concatenate([trainy, np.zeros([np.shape(trainy)[0], 1])], axis=1)
    m = trainx.shape[0]

    # load test data
    f2 = open(FLAGS.test_dir, 'rb')
    dict = pickle.load(f2)
    testx = dict['data']
    testy = dict['label']
    testy = np.concatenate([testy, np.zeros([np.shape(testy)[0], 1])], axis=1)



    # trainx, trainy = cifar10_input._get_dataset(FLAGS.data_dir, 'train')  # float [-1 1] images
    # testx, testy = cifar10_input._get_dataset(FLAGS.data_dir, 'test')
    # trainx_unl = trainx.copy()
    # trainx_unl2 = trainx.copy()

    if FLAGS.validation:
        split = int(0.1 * trainx.shape[0])
        print("validation enabled")
        testx  = trainx[:split]
        testy  = trainy[:split]
        trainx = trainx[split:]
        trainy = trainy[split:]

    nr_batches_train = int(trainx.shape[0] / FLAGS.batch_size)
    nr_batches_test = int(testx.shape[0] / FLAGS.batch_size)

    # select labeled data
    inds = rng_data.permutation(trainx.shape[0])
    trainx = trainx[inds]
    trainy = trainy[inds]

    trainx_unl = trainx.copy()
    trainx_unl2 = trainx.copy()
    txs = []
    tys = []
    eyes = np.eye(8, 8, dtype=np.uint8)
    for i in range(8):
        for j in range(m):
            if (trainy[j] == eyes[i]).all():
                txs.append(trainx[j])
                tys.append(trainy[j])
                txs = txs[0:FLAGS.labeled * (i + 1)]
                tys = tys[0:FLAGS.labeled * (i + 1)]

    txs = np.array(txs)
    tys = np.array(tys)



    # for j in range(10):
    #     txs.append(trainx[trainy == j][:FLAGS.labeled])
    #     tys.append(trainy[trainy == j][:FLAGS.labeled])
    # txs = np.concatenate(txs, axis=0)
    # tys = np.concatenate(tys, axis=0)

    '''construct graph'''
    unl = tf.placeholder(tf.float32, [FLAGS.batch_size, 128 * 128 * 1], name='unlabeled_data_input_pl')
    is_training_pl = tf.placeholder(tf.bool, [], name='is_training_pl')
    inp = tf.placeholder(tf.float32, [FLAGS.batch_size, 128 * 128 * 1], name='labeled_data_input_pl')
    lbl = tf.placeholder(tf.int32, [FLAGS.batch_size, 8], name='lbl_input_pl')
    # scalar pl
    lr_pl = tf.placeholder(tf.float32, [], name='learning_rate_pl')
    acc_train_pl = tf.placeholder(tf.float32, [], 'acc_train_pl')
    acc_test_pl = tf.placeholder(tf.float32, [], 'acc_test_pl')
    acc_test_pl_ema = tf.placeholder(tf.float32, [], 'acc_test_pl')

    random_z = tf.random_uniform([FLAGS.batch_size, 100], name='random_z')
    generator(random_z, is_training_pl, init=True)  # init of weightnorm weights
    gen_inp = generator(random_z, is_training_pl, init=False, reuse=True)
    discriminator(unl, is_training_pl, init=True)
    logits_lab, _ = discriminator(inp, is_training_pl, init=False, reuse=True)
    logits_gen, layer_fake = discriminator(gen_inp, is_training_pl, init=False, reuse=True)
    logits_unl, layer_real = discriminator(unl, is_training_pl, init=False, reuse=True)

    with tf.name_scope('loss_functions'):
        # discriminator
        epsilon = 1e-8
        l_lab = tf.reduce_mean(tf.nn.softmax_cross_entropy_with_logits_v2(logits=logits_lab, labels=lbl))

        prob_lab = tf.nn.softmax(logits_unl)
        prob_unlabel_be_unlabel = 1 - prob_lab[:, -1] + epsilon
        tmp_log = tf.log(prob_unlabel_be_unlabel)
        l_unl = -1 * tf.reduce_mean(tmp_log)

        prob_gen = tf.nn.softmax(logits_gen)
        prob_fake_be_fake = prob_gen[:, -1] + epsilon
        tmp_log = tf.log(prob_fake_be_fake)
        l_gen = -1 * tf.reduce_mean(tmp_log)

        loss_lab = l_lab
        loss_unl = l_unl+l_gen
        #generator
        m1 = tf.reduce_mean(layer_real, axis=0)
        m2 = tf.reduce_mean(layer_fake, axis=0)

        loss_dis = FLAGS.unl_weight * loss_unl + FLAGS.lbl_weight * loss_lab
        loss_gen = tf.reduce_mean(tf.square(m1 - m2))
        correct_pred = tf.equal(tf.cast(tf.argmax(logits_lab, 1), tf.int32), tf.cast(tf.argmax(lbl, 1), tf.int32))
        accuracy_classifier = tf.reduce_mean(tf.cast(correct_pred, tf.float32))


#=======================================================================================================================
    # with tf.name_scope('loss_functions'):
    #     # discriminator
    #
    #     l_unl = tf.reduce_logsumexp(logits_unl, axis=1)
    #     l_gen = tf.reduce_logsumexp(logits_gen, axis=1)
    #     loss_lab = tf.reduce_mean(tf.nn.softmax_cross_entropy_with_logits(logits=logits_lab, labels=lbl))
    #     loss_unl = - 0.5 * tf.reduce_mean(l_unl) \
    #                + 0.5 * tf.reduce_mean(tf.nn.softplus(l_unl)) \
    #                + 0.5 * tf.reduce_mean(tf.nn.softplus(l_gen))
    #
    #     # loss_unl= 0.5*entropy_1(logits_unl) +  0.5 * tf.reduce_mean(tf.nn.softplus(l_gen))


        # generator
        # m1 = tf.reduce_mean(layer_real, axis=0)
        # m2 = tf.reduce_mean(layer_fake, axis=0)
        #
        # loss_dis = FLAGS.unl_weight * loss_unl + FLAGS.lbl_weight * loss_lab
        # loss_gen = tf.reduce_mean(tf.square(m1 - m2))
        # correct_pred = tf.equal(tf.cast(tf.argmax(logits_lab, 1), tf.int32), tf.cast(tf.argmax(lbl, 1), tf.int32))
        # accuracy_classifier = tf.reduce_mean(tf.cast(correct_pred, tf.float32))

#=======================================================================================================================

    with tf.name_scope('optimizers'):
        # control op dependencies for batch norm and trainable variables
        tvars = tf.trainable_variables()
        dvars = [var for var in tvars if 'discriminator_model' in var.name]
        gvars = [var for var in tvars if 'generator_model' in var.name]

        update_ops = tf.get_collection(tf.GraphKeys.UPDATE_OPS)
        update_ops_gen = [x for x in update_ops if ('generator_model' in x.name)]
        update_ops_dis = [x for x in update_ops if ('discriminator_model' in x.name)]
        optimizer_dis = tf.train.AdamOptimizer(learning_rate=lr_pl, beta1=0.5, name='dis_optimizer')
        optimizer_gen = tf.train.AdamOptimizer(learning_rate=lr_pl, beta1=0.5, name='gen_optimizer')

        with tf.control_dependencies(update_ops_gen):
            train_gen_op = optimizer_gen.minimize(loss_gen, var_list=gvars)

        dis_op = optimizer_dis.minimize(loss_dis, var_list=dvars)
        ema = tf.train.ExponentialMovingAverage(decay=FLAGS.ma_decay)       #滑动平均
        maintain_averages_op = ema.apply(dvars)

        with tf.control_dependencies([dis_op]):
            train_dis_op = tf.group(maintain_averages_op)

        logits_ema, _ = discriminator(inp, is_training_pl, getter=get_getter(ema), reuse=True)
        correct_pred_ema = tf.equal(tf.cast(tf.argmax(logits_ema, 1), tf.int32), tf.cast(tf.argmax(lbl, 1), tf.int32))
        accuracy_ema = tf.reduce_mean(tf.cast(correct_pred_ema, tf.float32))

    with tf.name_scope('summary'):
        with tf.name_scope('discriminator'):
            tf.summary.scalar('loss_discriminator', loss_dis, ['dis'])

        with tf.name_scope('generator'):
            tf.summary.scalar('loss_generator', loss_gen, ['gen'])

        with tf.name_scope('images'):
            tf.summary.image('gen_images', gen_inp, 10, ['image'])

        with tf.name_scope('epoch'):
            tf.summary.scalar('accuracy_train', acc_train_pl, ['epoch'])
            tf.summary.scalar('accuracy_test_moving_average', acc_test_pl_ema, ['epoch'])
            tf.summary.scalar('accuracy_test', acc_test_pl, ['epoch'])
            tf.summary.scalar('learning_rate', lr_pl, ['epoch'])

        sum_op_dis = tf.summary.merge_all('dis')
        sum_op_gen = tf.summary.merge_all('gen')
        sum_op_im = tf.summary.merge_all('image')
        sum_op_epoch = tf.summary.merge_all('epoch')

    # training global varialble
    global_epoch = tf.Variable(0, trainable=False, name='global_epoch')
    global_step = tf.Variable(0, trainable=False, name='global_step')
    inc_global_step = tf.assign(global_step, global_step+1)            # global_step  += 1
    inc_global_epoch = tf.assign(global_epoch, global_epoch+1)         # global_epoch += 1

    # op initializer for session manager
    init_gen = [var.initializer for var in gvars][:-3]
    with tf.control_dependencies(init_gen):
        op = tf.global_variables_initializer()
    init_feed_dict = {inp: trainx_unl[:FLAGS.batch_size], unl: trainx_unl[:FLAGS.batch_size], is_training_pl: True}

    sv = tf.train.Supervisor(logdir=FLAGS.logdir, global_step=global_epoch, summary_op=None, save_model_secs=0,
                             init_op=op,init_feed_dict=init_feed_dict)

    '''//////training //////'''
    print('start training')
    with sv.managed_session() as sess:
        tf.set_random_seed(rng.randint(2 ** 10))
        print('\ninitialization done')
        print('Starting training from epoch :%d, step:%d \n'%(sess.run(global_epoch),sess.run(global_step)))

        writer = tf.summary.FileWriter(FLAGS.logdir, sess.graph)

        while not sv.should_stop():
            epoch = sess.run(global_epoch)
            train_batch = sess.run(global_step)

            if (epoch >= FLAGS.epoch):
                print("Training done")
                sv.stop()
                break

            begin = time.time()
            train_loss_lab=train_loss_unl=train_loss_gen=train_acc=test_acc=test_acc_ma= 0
            lr = FLAGS.learning_rate * linear_decay(FLAGS.decay_start,FLAGS.epoch,epoch)

            # construct randomly permuted batches
            trainx = []
            trainy = []
            for t in range(int(np.ceil(trainx_unl.shape[0] / float(txs.shape[0])))):  # same size lbl and unlb
                inds = rng.permutation(txs.shape[0])
                trainx.append(txs[inds])
                trainy.append(tys[inds])
            trainx = np.concatenate(trainx, axis=0)
            trainy = np.concatenate(trainy, axis=0)
            trainx_unl = trainx_unl[rng.permutation(trainx_unl.shape[0])]  # shuffling unl dataset
            trainx_unl2 = trainx_unl2[rng.permutation(trainx_unl2.shape[0])]

            # training
            for t in range(nr_batches_train):

                display_progression_epoch(t, nr_batches_train)
                ran_from = t * FLAGS.batch_size
                ran_to = (t + 1) * FLAGS.batch_size

                # train discriminator
                feed_dict = {unl: trainx_unl[ran_from:ran_to],
                             is_training_pl: True,
                             inp: trainx[ran_from:ran_to],
                             lbl: trainy[ran_from:ran_to],
                             lr_pl: lr}
                _, acc, lu, lb, sm = sess.run([train_dis_op, accuracy_classifier, loss_lab, loss_unl, sum_op_dis],
                                              feed_dict=feed_dict)

                train_loss_unl += lu
                train_loss_lab += lb
                train_acc += acc
                if (train_batch % FLAGS.step_print) == 0:
                    writer.add_summary(sm, train_batch)

                # train generator
                _, lg, sm = sess.run([train_gen_op, loss_gen, sum_op_gen], feed_dict={unl: trainx_unl2[ran_from:ran_to],
                                                                                      is_training_pl: True,
                                                                                      lr_pl: lr})
                train_loss_gen += lg
                if (train_batch % FLAGS.step_print) == 0:
                    writer.add_summary(sm, train_batch)

                if (train_batch % FLAGS.freq_print == 0) & (train_batch != 0):
                    ran_from = np.random.randint(0, trainx_unl.shape[0] - FLAGS.batch_size)
                    ran_to = ran_from + FLAGS.batch_size
                    sm = sess.run(sum_op_im,
                                  feed_dict={is_training_pl: True, unl: trainx_unl[ran_from:ran_to]})
                    writer.add_summary(sm, train_batch)

                train_batch += 1
                sess.run(inc_global_step)

            train_loss_lab /= nr_batches_train
            train_loss_unl /= nr_batches_train
            train_loss_gen /= nr_batches_train
            train_acc /= nr_batches_train

            # Testing moving averaged model and raw model
            if (epoch % FLAGS.freq_test == 0) | (epoch == FLAGS.epoch-1):
                for t in range(nr_batches_test):
                    ran_from = t * FLAGS.batch_size
                    ran_to = (t + 1) * FLAGS.batch_size
                    feed_dict = {inp: testx[ran_from:ran_to],
                                 lbl: testy[ran_from:ran_to],
                                 is_training_pl: False}
                    acc, acc_ema = sess.run([accuracy_classifier, accuracy_ema], feed_dict=feed_dict)
                    test_acc += acc
                    test_acc_ma += acc_ema
                test_acc /= nr_batches_test
                test_acc_ma /= nr_batches_test

                sum = sess.run(sum_op_epoch, feed_dict={acc_train_pl: train_acc,
                                                        acc_test_pl: test_acc,
                                                        acc_test_pl_ema: test_acc_ma,
                                                        lr_pl: lr})
                writer.add_summary(sum, epoch)

                print(
                    "Epoch %d | time = %ds | loss gen = %.4f | loss lab = %.4f | loss unl = %.4f "
                    "| train acc = %.4f| test acc = %.4f | test acc ema = %0.4f"

                    % (epoch, time.time() - begin, train_loss_gen, train_loss_lab, train_loss_unl, train_acc,
                       test_acc, test_acc_ma))

            sess.run(inc_global_epoch)

            # save snapshots of model
            if ((epoch % FLAGS.freq_save == 0) & (epoch!=0) ) | (epoch == FLAGS.epoch-1):
                string = 'model-' + str(epoch)
                save_path = os.path.join(FLAGS.logdir, string)
                sv.saver.save(sess, save_path)
                print("Model saved in file: %s" % (save_path))


if __name__ == '__main__':
    tf.app.run()
