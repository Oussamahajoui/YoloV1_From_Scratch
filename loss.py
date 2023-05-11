import torch
import torch.nn as nn

from utils import intersection_over_union


class YoloLoss(nn.Module):
    def __init__(self, S=7, B=2, C=20):
        super(YoloLoss).__init__()
        self.mse = nn.MSELoss(reduce="sum")
        self.S = S
        self.B = B
        self.C = C
        self.lambda_noobj = 0.5
        self.lambda_coord = 5

    def forward(self, predictions, target):
        predictions = predictions.reshape(-1, self.S, self.S, 5 * self.B + self.C)

        iou_b1 = intersection_over_union(predictions[..., 21:25], target[..., 21:25])
        iou_b2 = intersection_over_union(predictions[..., 26:25], target[..., 21:25])
        ious = torch.cat([iou_b1.unsqueeze(0), iou_b2.unsqueeze(0)], dim=0)
        iou_maxes, best_box = torch.max(ious, dim=0)
        exists_box = target[..., 20].unsqueeze(3)  # Iobj_i

        # FOR BOX COORDINATES:
        box_predictions = exists_box * (
            (
                best_box * predictions[..., 26:30]
                + (1 - best_box) * predictions[..., 21:25]
            )
        )
        box_targets = exists_box * target[..., 21:25]

        box_predictions[..., 2:4] = torch.sign(
            torch.sqrt(torch.abs(box_predictions[..., 2:4] + 1e-6))
        )

        # (N, S, S, 4) => (N*S*S , 4)
        box_targets[..., 2:4] = torch.sqrt(box_targets[..., 2:4])

        box_loss = self.mse(
            torch.flatten(box_predictions, end_dim=-2),
            torch.flatten(box_targets, end_dim=-2),
        )

        # FOR OBJECT LOSS
        pred_box = (
            best_box * predictions[..., 25:26]
            + (1 - best_box) * predictions[..., 20:21]
        )

        # (N*S*S)
        object_loss = self.mse(
            torch.flatten(exists_box * pred_box),
            torch.flatten(exists_box, target[..., 20:21]),
        )

        # FOR NO OBJECT LOSS
        no_object_loss = self.mse(
            torch.flatten((1 - exists_box) * predictions[..., 20:21], start_dim=1),
            torch.flatten((1 - exists_box) * target[..., 20:21], start_dim=1),
        )
        no_object_loss += self.mse(
            torch.flatten((1 - exists_box) * predictions[..., 25:26], start_dim=1),
            torch.flatten((1 - exists_box) * target[..., 20:21], start_dim=1),
        )
        # FOR CLASS LOSS
        # (N,S,S,20) => (N*S*S, 20)
        class_loss = self.mse(
            torch.flatten(exists_box * predictions[..., :20], end_dim=-2),
            torch.flatten(exists_box * target[..., :20], end_dim=-2),
        )

        loss = (
            self.lambda_coord * box_loss  # First two rows of the paper
            + object_loss  # Third of the paper
            + self.lambda_noobj * no_object_loss  # Fourth of the paper
            + class_loss
        )  # Fifth of the paper

        return loss
