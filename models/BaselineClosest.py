import time

import cv2
import numpy as np

from Game import GamesManager


class BaselineClosest:
    def __init__(self, p_random=0.01, length_random=10, state_size=800):
        self.state_size = state_size
        self.p_random = p_random
        self.length_random = length_random
        self.is_on_random = False
        self.random_target = (None, None)
        self.random_time_to_live = 0

        meshgrid = np.meshgrid(range(self.state_size), range(self.state_size), indexing="ij")
        self.coordinates = np.concatenate([meshgrid[0].flatten().reshape((-1, 1)), meshgrid[1].flatten().reshape((-1, 1))], axis=1)
        center = np.array([(state_size-1)/2, (state_size-1)/2]) # the -1 is very non-intuitive but correct
        self.distance_matrix = np.linalg.norm(self.coordinates - center, axis=1)

    def evaluate(self, game_engine, n_greedy, max_steps, animate=False):
        print("###### EVALUATION ###### \n\n\n")

        games_dict = game_engine.request_new_games(n_games=n_greedy, name="test", pooled=False)
        identifiers = list(games_dict.keys())

        sum_rewards = {id: 0 for id in identifiers}
        games_alive = {id for id in identifiers}
        terminaison_steps = {id: 0 for id in identifiers}
        remaining_pallets = {id: 0 for id in identifiers}
        step = 0

        drawing_size = self.state_size
        if animate:
            n_columns_windows = 7
            positions_windows = {}
            for index_agent, game in enumerate(games_dict.values()):
                x_window = index_agent % n_columns_windows
                y_window = int(index_agent / n_columns_windows)
                x_window = (x_window * (drawing_size + 50)) + 50
                y_window = (y_window * (drawing_size + 50)) + 50
                positions_windows[game.get_identifier()] = [x_window, y_window]

        while True:
            print(step)
            if step > max_steps:
                for game in games_dict.values():
                    cv2.waitKey(1)
                    cv2.destroyWindow(str(game.get_identifier()))
                    cv2.waitKey(1)
                break

            actions_buffer = dict()
            for index, (id, game) in enumerate(games_dict.items()):
                frame = game.get_current_state()["last_frame"]
                (input_x, input_y) = self.action(frame)
                actions_buffer[id] = {"input_x": input_x.astype(float), "input_y": input_y.astype(float)}

            new_states_list = game_engine.act_and_observe(actions_buffer, replace_terminal_game=False, max_steps=max_steps)

            for index_agent, new_state_dict in enumerate(new_states_list):
                if new_state_dict["is_terminal"] == 1.0:
                    games_dict.pop(new_state_dict["identifier"])
                    games_alive.remove(new_state_dict["identifier"])
                    terminaison_steps[new_state_dict["identifier"]] += step
                    remaining_pallets[new_state_dict["identifier"]] = new_state_dict["remaining_pallets"]
                    print("Died after {} steps".format(terminaison_steps[new_state_dict["identifier"]]))

                new_state = new_state_dict["last_frame"]
                if animate and new_state_dict["is_terminal"] == 0.0:
                    [x_window, y_window] = positions_windows[new_state_dict["identifier"]]

                    game_engine.get_game(new_state_dict["identifier"]).animate(frame=new_state,
                                                                                    x_window=x_window,
                                                                                    y_window=y_window)
                sum_rewards[new_state_dict["identifier"]] += new_state_dict["reward"]


            step += 1

            if len(games_alive) == 0:
                break

        print("Greedy: \n  "
              "Terminated at steps: {} \n  "
              "Remaining pallets {}\n  "
              "  Average remaining pallets {} ; Std remainig pallets {}\n"
              "Total rewards: {} \n"
              "  Average rewards: {} ; Std rewards: {}".
              format(list(terminaison_steps.values()),
                     list(remaining_pallets.values()),
                     np.mean(list(remaining_pallets.values())),
                     np.std(list(remaining_pallets.values())),
                     list(sum_rewards.values()),
                     np.mean(list(sum_rewards.values())),
                     np.std(list(sum_rewards.values()))))

    def action(self, frame):
        if self.is_on_random == False:
            coin_flip = np.random.binomial(n=1, p=self.p_random)
            if coin_flip == 1:
                self.is_on_random = True
                self.random_target = np.random.uniform(low=0, high=self.state_size-1, size=2)
                self.random_time_to_live = self.length_random - 1
                target = self.random_target
            else:
                state = frame.flatten()
                mask = state == 1
                if mask.sum() == 0:
                    self.is_on_random = True
                    self.random_target = np.random.uniform(low=0, high=self.state_size - 1, size=2)
                    self.random_time_to_live = self.length_random - 1
                    target = self.random_target
                else:
                    target = mask * self.distance_matrix
                    target[target == 0] = np.infty
                    closest = np.argmin(target)
                    coordinate_closest = self.coordinates[closest]
                    target = coordinate_closest
        else:
            target = self.random_target
            self.random_time_to_live -= 1
            if self.random_time_to_live == 0:
                self.is_on_random = False

        return self.coordinate_to_input(target[1], target[0])

    """
        Convert the selected point on state/window/image to formatted input.
    """
    def coordinate_to_input(self, x, y):
        distance_from_center = ((x - self.state_size/2)**2 + (y - self.state_size/2)**2)**0.5

        max_distance = self.state_size / 4# assume square screen
        if distance_from_center >= max_distance:
            distance_from_center = max_distance


        if (x - self.state_size/2) == 0: # special case
            angle = np.pi/2
        else:
            angle = np.arctan((y - self.state_size/2)/(x - self.state_size/2))

        projection_x = np.cos(angle) * distance_from_center
        projection_y = np.sin(angle) * distance_from_center

        if (x - self.state_size / 2) < 0: # this is w.r.t x, not as usual, the reference frame is weird
            projection_x = - projection_x
            projection_y = - projection_y

        input_x = projection_x / max_distance
        input_y = projection_y / max_distance

        return (input_x, input_y)



if __name__ == "__main__":

    state_size = 64
    game_manager = GamesManager(state_size=state_size, n_pallets=20)
    bs = BaselineClosest(state_size=state_size)
    bs.evaluate(game_engine=game_manager, n_greedy=100, max_steps=200, animate=True)
