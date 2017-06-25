#!/usr/bin/env python
from __future__ import print_function
import cv2
import numpy as np
import time

import rospy

from sensor_msgs.msg import Image
from cv_bridge import CvBridge, CvBridgeError


class VideoFrames:
    def __init__(self, image_topic, target_x, target_y, target_w, target_h):
        self.image_sub = rospy.Subscriber(image_topic, Image, self.callback_image, queue_size=1)
        self.bridge = CvBridge()
        self.frames = []
        self.target_x, self.target_y, self.target_w, self.target_h = target_x, target_y, target_w, target_h

    def callback_image(self, data):
        try:
            cv_image = self.bridge.imgmsg_to_cv2(data, "bgr8")
        except CvBridgeError as e:
            rospy.logerr('[ros-video-recorder][VideoFrames] Converting Image Error. ' + str(e))
            return

        self.frames.append((time.time(), cv_image))

    def get_latest(self, at_time, remove_older=True):
        fs = [x for x in self.frames if x[0] <= at_time]
        if len(fs) == 0:
            return None

        f = fs[-1]
        if remove_older:
            self.frames = self.frames[len(fs) - 1:]

        return f[1]


class VideoRecorder:
    def __init__(self, output_width, output_height, output_fps, output_format, output_path):
        self.frame_wrappers = []
        self.start_time = -1
        self.end_time = -1

        self.fps = output_fps
        self.interval = 1.0 / self.fps
        self.output_width = output_width
        self.output_height = output_height

        # output
        fourcc = cv2.cv.FOURCC(*output_format)
        self.video_writer = cv2.VideoWriter(output_path, fourcc, output_fps, (output_width, output_height))

    def add_subscription(self, subscription):
        self.frame_wrappers.append(subscription)

    def start_record(self):
        self.start_time = time.time()
        curr_time = self.start_time
        while self.end_time < 0 or curr_time <= self.end_time:
            try:
                canvas = np.zeros((self.output_height, self.output_width, 3), np.uint8)

                for frame_w in self.frame_wrappers:
                    f = frame_w.get_latest(at_time=curr_time)
                    if f is None:
                        continue

                    resized = cv2.resize(f, (frame_w.target_w, frame_w.target_h))
                    canvas[frame_w.target_y:frame_w.target_y+frame_w.target_h, frame_w.target_x:frame_w.target_x+frame_w.target_w] = resized
                    rospy.sleep(0.01)

                self.video_writer.write(canvas)
                rospy.sleep(0.01)

                if rospy.is_shutdown() and self.end_time < 0:
                    self.terminate()

                while curr_time + self.interval > time.time():
                    rospy.sleep(self.interval)

                curr_time += self.interval
            except KeyboardInterrupt:
                self.terminate()
                continue

        self.video_writer.release()

    def terminate(self):
        rospy.loginfo("[ros-video-recorder] Video Saved.")
        self.end_time = time.time()


if __name__ == '__main__':
    rospy.init_node('video_recorder', anonymous=True)

    # parameters
    output_width = int(rospy.get_param('~output_width', '640'))
    output_height = int(rospy.get_param('~output_height', '480'))
    output_fps = int(rospy.get_param('~output_fps', '30'))
    output_format = rospy.get_param('~output_format', 'xvid')
    output_path = rospy.get_param('~output_path', '')
    num_videos = int(rospy.get_param('~num_videos', '1000'))

    assert output_format, 'error. output_path is not provided.'

    ft = VideoRecorder(output_width, output_height, output_fps, output_format, output_path)

    # get parameters for videos and initialize subscriptions
    for idx in range(1000):
        source_info = rospy.get_param('~source%d' % (idx+1), '')
        if not source_info:
            break
        source_info_list = source_info.split(',')

        source_topic = source_info_list[0].strip()
        target_x = int(source_info_list[1])
        target_y = int(source_info_list[2])
        target_w = int(source_info_list[3])
        target_h = int(source_info_list[4])

        vf = VideoFrames(source_topic, target_x, target_y, target_w, target_h)
        ft.add_subscription(vf)

    # recording.
    try:
        ft.start_record()
    except KeyboardInterrupt:
        rospy.logerr("[ros-video-recorder] Shutting down+")

    ft.terminate()
