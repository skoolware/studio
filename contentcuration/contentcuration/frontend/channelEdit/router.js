import VueRouter from 'vue-router';
import { RouterNames } from './constants';
import TreeView from './views/TreeView';
import store from './store';
import ImportFromChannelsIndex from './views/ImportFromChannels/ImportFromChannelsIndex';
import SearchOrBrowseWindow from './views/ImportFromChannels/SearchOrBrowseWindow';
import ReviewSelectionsPage from './views/ImportFromChannels/ReviewSelectionsPage';
import { RouterNames as ChannelRouterNames } from 'frontend/channelList/constants';
import Sandbox from 'shared/views/Sandbox';
import ChannelModal from 'shared/views/channel/ChannelModal';
import ChannelDetailsModal from 'shared/views/channel/ChannelDetailsModal';
import EditModal from 'edit_channel/uploader/views/EditModal';

const router = new VueRouter({
  routes: [
    {
      name: RouterNames.SANDBOX,
      path: '/sandbox/:nodeId',
      props: true,
      component: Sandbox,
      beforeEnter: (to, from, next) => {
        const channelPromise = store.dispatch(
          'channel/loadChannel',
          store.state.currentChannel.currentChannelId
        );
        const treePromise = store.dispatch(
          'contentNode/loadTree',
          store.state.currentChannel.currentChannelId
        );
        const nodePromise = store.dispatch('contentNode/loadContentNode', to.params.nodeId);
        // api call to get ancestors if nodeId is a child descendant???
        return Promise.all([channelPromise, treePromise, nodePromise])
          .then(() => next())
          .catch(() => {});
      },
    },
    {
      name: RouterNames.TREE_ROOT_VIEW,
      path: '/',
      beforeEnter: (to, from, next) => {
        return store
          .dispatch('channel/loadChannel', store.state.currentChannel.currentChannelId)
          .then(channel => {
            const nodeId = channel.root_id;
            return next({
              name: RouterNames.TREE_VIEW,
              params: {
                nodeId,
              },
            });
          });
      },
    },
    {
      name: RouterNames.IMPORT_FROM_CHANNELS,
      path: '/import/:destNodeId',
      component: ImportFromChannelsIndex,
      props: {
        isOpen: true,
      },
      children: [
        {
          name: RouterNames.IMPORT_FROM_CHANNELS_BROWSE,
          path: 'browse/:channelId?/:nodeId?',
          component: SearchOrBrowseWindow,
          props: {
            currentView: 'browse',
          },
        },
        {
          name: RouterNames.IMPORT_FROM_CHANNELS_SEARCH,
          path: 'search/:searchTerm',
          component: SearchOrBrowseWindow,
          props: {
            currentView: 'search',
          },
        },
        {
          name: RouterNames.IMPORT_FROM_CHANNELS_REVIEW,
          path: 'review',
          component: ReviewSelectionsPage,
        },
      ],
    },
    {
      name: RouterNames.TREE_VIEW,
      path: '/:nodeId/:detailNodeId?',
      props: true,
      component: TreeView,
      beforeEnter: (to, from, next) => {
        const channelPromise = store.dispatch(
          'channel/loadChannel',
          store.state.currentChannel.currentChannelId
        );
        const treePromise = store.dispatch(
          'contentNode/loadTree',
          store.state.currentChannel.currentChannelId
        );
        return Promise.all([channelPromise, treePromise])
          .then(() => next())
          .catch(() => {});
      },
      children: [
        {
          name: RouterNames.CONTENTNODE_DETAILS,
          path: 'details/:detailNodeIds',
          props: true,
          component: EditModal,
        },
        {
          name: RouterNames.ADD_TOPICS,
          path: 'topics/:detailNodeIds',
          props: true,
          component: EditModal,
        },
        {
          name: RouterNames.ADD_EXERCISE,
          path: 'exercise/:detailNodeIds',
          props: true,
          component: EditModal,
        },
        {
          name: RouterNames.UPLOAD_FILES,
          path: 'upload/:detailNodeIds?',
          props: true,
          component: EditModal,
        },
        {
          name: ChannelRouterNames.CHANNEL_DETAILS,
          path: 'channel/:channelId/details',
          component: ChannelDetailsModal,
          props: true,
        },
        {
          name: ChannelRouterNames.CHANNEL_EDIT,
          path: 'channel/:channelId/edit',
          component: ChannelModal,
          props: true,
        },
      ],
    },
  ],
});

export default router;