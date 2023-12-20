import slope
import slope.nn as nn

import time
import numpy as np
from tqdm import tqdm

import numpy as np
from lib.datasets.cifar10 import get_cifar10
from lib.models.cv.resnet_cifar import resnet

@slope.jit
def train_step(model, batch, optimizer):
    def train_loss_fn(model, batch):
        x, y = batch
        logits, model = model(x, training=True)
        loss = logits.cross_entropy(y) / x.size(0)
        
        return loss, (model, logits)
    (loss, (model, logits)), grad_model = slope.value_and_grad(train_loss_fn, has_aux=True)(model, batch)
    model, optimizer = optimizer(model, grad_model)
    return loss, logits, model, optimizer, grad_model

@slope.jit
def test_step(model, batch):
    x, y = batch
    logits = model(x, training=False)
    loss = logits.cross_entropy(y) / x.size(0)
    return loss, logits

def get_dataloader(images, labels, batch_size, shuffle=False):
    N = images.shape[0]
    perm = np.random.permutation(N) if shuffle else np.arange(N)

    mean = slope.tensor([0.4913997551666284, 0.48215855929893703, 0.4465309133731618], dtype=slope.float32)[None, ..., None, None]
    std = slope.tensor([0.24703225141799082, 0.24348516474564, 0.26158783926049628], dtype=slope.float32)[None, ..., None, None]

    def data_iter():
        for i in range(N//batch_size):
            batch_idx = perm[i * batch_size : (i + 1) * batch_size]
            x = ((slope.tensor(images[batch_idx], dtype=slope.float32)) - mean) / std
            y = slope.tensor(labels[batch_idx], dtype=slope.int32)
            yield x, y
    nbatches = images.shape[0] // batch_size + (1 if (images.shape[0] % batch_size != 0) else 0)
    return data_iter, nbatches
        

if __name__ == "__main__":
    nepochs = 100
    train_batch_size = 50 # TODO: must be multiple of dataset
    test_batch_size = 50
    train_images, train_labels, test_images, test_labels = get_cifar10()
    
    model = resnet(depth=8)
    # optimizer = nn.AdamW(model, lr=0.05)#,weight_decay=1e-5)
    optimizer = nn.SGD(model, lr=0.1, momentum=0.9, weight_decay=1e-5)
    # optimizer = nn.SGD(model, lr=0., momentum=0., weight_decay=0)
    
    train_dataloader, ntrain_batches = get_dataloader(train_images, train_labels, train_batch_size, shuffle=True)
    test_dataloader, ntest_batches = get_dataloader(test_images, test_labels, test_batch_size, shuffle=False)

    print("\nStarting training...")
    best_acc = 0.
    for epoch in range(nepochs):
        total_loss = 0.
        true_positives = 0.
        
        for i, batch in (pbar := tqdm(enumerate(train_dataloader()))):
            loss, logits, model, optimizer, grad_model = train_step(model, batch, optimizer)
            loss_numpy =  float(loss.numpy())
            total_loss += loss_numpy
            y_hat, y =  logits.argmax(-1), batch[1]
            true_positives += float((y_hat == y).cast(slope.float32).sum().numpy())
            train_loss = total_loss/(i+1)
            train_acc = true_positives/ (train_batch_size * (i+1))
            msg = (f"Train epoch: {epoch}, batch: {i+1}/{ntrain_batches}, "
                   f"batch_loss: {loss_numpy:.4f}, "
                   f"loss: {train_loss:.4f}, acc: {train_acc:.4f}")
            pbar.set_description(msg)
            if i % 200 == 0:
                print(f"\n{model.bn1.running_mean=}")
                print(f"{model.bn1.running_var=}\n")
            # if i == 5:break

        total_loss = 0.
        true_positives = 0.
        for i, batch in (pbar := tqdm(enumerate(test_dataloader()))):
            loss, logits, = test_step(model, batch)
            loss_numpy =  float(loss.numpy())
            total_loss += loss_numpy
            y_hat, y =  logits.argmax(-1), batch[1]
            true_positives += float((y_hat == y).cast(slope.float32).sum().numpy())
            test_loss = total_loss/(i+1)
            test_acc = true_positives/ (test_batch_size * (i+1))
            msg = (f"Test epoch: {epoch}, batch: {i+1}/{ntest_batches}, "
                   f"batch_loss: {loss_numpy:.4f}, "
                   f"loss: {test_loss:.4f}, acc: {test_acc:.4f}")
            pbar.set_description(msg)
            # if i == 5:break
        if test_acc > best_acc:
            print(f"Best accuracy {test_acc:.2f} at epoch {epoch}")
            best_acc = test_acc

# def test_all(model, x, y):
#     out = model(x)
#     y_hat2 = np.argmax(out.numpy() ,-1)
#     corrects2 = (y_hat2 == y.numpy()).astype(np.float32)
#     accuracy2 = np.mean(corrects2)
#     return accuracy2
