import os

import torch
from torch import optim
from torchvision.utils import save_image

import boilr
from boilr import VIExperimentManager
from boilr.viz import img_grid_pad_value
from models.mnist_vae import MnistVAE
from .data import DatasetManager

boilr.set_options(model_print_depth=2)

class MnistExperiment(VIExperimentManager):
    """
    Experiment manager.

    Data attributes:
    - 'args': argparse.Namespace containing all config parameters. When
      initializing this object, if 'args' is not given, all config
      parameters are set based on experiment defaults and user input, using
      argparse.
    - 'run_description': string description of the run that includes a timestamp
      and can be used e.g. as folder name for logging.
    - 'model': the model.
    - 'device': torch.device that is being used
    - 'dataloaders': DataLoaders, with attributes 'train' and 'test'
    - 'optimizer': the optimizer
    """

    def make_datamanager(self):
        cuda = self.device.type == 'cuda'
        return DatasetManager(self.args, cuda)

    def make_model(self):
        return MnistVAE()

    def make_optimizer(self):
        return optim.Adam(self.model.parameters(),
                          lr=self.args.lr,
                          weight_decay=self.args.weight_decay)


    def forward_pass(self, x, y=None):
        """
        Simple single-pass model evaluation. It consists of a forward pass
        and computation of all necessary losses and metrics.
        """

        x = x.to(self.device, non_blocking=True)
        out = self.model(x)
        elbo_sep = out['elbo']
        elbo = elbo_sep.mean()
        loss = - elbo

        out = {
            'out_sample': out['sample'],
            'out_mean': out['mean'],
            'loss': loss,
            'elbo_sep': elbo_sep,
            'elbo/elbo': elbo,
            'elbo/recons': out['nll'].mean(),
            'elbo/kl': out['kl'].mean(),
        }
        return out


    def additional_testing(self, img_folder):
        """
        Perform additional testing, including possibly generating images.

        In this case, save samples from the generative model, and pairs
        input/reconstruction from the test set.

        :param img_folder: folder to store images
        """

        step = self.model.global_step

        if not self.args.dry_run:

            # Saved images will have n**2 sub-images
            n = 8

            # Save model samples
            sample = self.model.sample_prior(n ** 2)
            fname = os.path.join(img_folder, 'sample_' + str(step) + '.png')
            pad = img_grid_pad_value(sample)
            save_image(sample, fname, nrow=n, pad_value=pad)

            # Get first test batch
            (x, _) = next(iter(self.dataloaders.test))
            fname = os.path.join(img_folder, 'reconstruction_' + str(step) + '.png')

            # Save model original/reconstructions
            self.save_input_and_recons(x, fname, n)


    def save_input_and_recons(self, x, fname, n):
        n_img = n ** 2 // 2
        if x.shape[0] < n_img:
            msg = ("{} data points required, but given batch has size {}. "
                   "Please use a larger batch.".format(n_img, x.shape[0]))
            raise RuntimeError(msg)
        x = x.to(self.device)
        outputs = self.forward_pass(x)
        x = x[:n_img]
        recons = outputs['out_sample'][:n_img]
        imgs = torch.stack([x.cpu(), recons.cpu()])
        imgs = imgs.permute(1, 0, 2, 3, 4)
        imgs = imgs.reshape(n ** 2, x.size(1), x.size(2), x.size(3))
        pad = img_grid_pad_value(imgs)
        save_image(imgs, fname, nrow=n, pad_value=pad)


    def _parse_args(self, parser):
        """
        Parse command-line arguments defining experiment settings.

        :param: parser

        :return: args: argparse.Namespace with experiment settings
        """

        self.add_required_args(parser,

                               # General
                               batch_size=64,
                               test_batch_size=1000,
                               lr=1e-3,
                               seed=54321,
                               train_log_every=1000,
                               test_log_every=1000,
                               checkpoint_every=10000,
                               resume="",

                               # VI-specific
                               loglikelihood_every=50000,
                               loglikelihood_samples=100, )

        parser.add_argument('--wd',
                            type=float,
                            default=0.0,
                            dest='weight_decay',
                            help='weight decay')

        args = parser.parse_args()

        assert args.loglikelihood_every % args.test_log_every == 0

        return args

    @staticmethod
    def _make_run_description(args):
        """
        Create a string description of the run. It is used in the names of the
        logging folders.

        :param args: experiment config
        :return: the run description
        """
        s = ''
        s += 'seed{}'.format(args.seed)
        if len(args.additional_descr) > 0:
            s += ',' + args.additional_descr
        return s
